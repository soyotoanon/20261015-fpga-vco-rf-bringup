from __future__ import annotations

import csv
import math
import queue
import statistics
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


class InstrumentError(RuntimeError):
    pass


def finite_number(value: object) -> float:
    try:
        number = float(str(value).strip())
    except Exception as exc:
        raise InstrumentError(f"示波器返回的数值无法解析：{value!r}") from exc
    if not math.isfinite(number) or abs(number) >= 1e20:
        raise InstrumentError(f"示波器返回无效数值：{number}")
    return number


@dataclass(frozen=True)
class Sample:
    index: int
    timestamp: str
    elapsed_s: float
    dac_v: float
    dds_amp: float
    freq_mhz: float
    expected_amp: float
    residual: float


def linear_fit(samples: list[Sample]) -> dict[str, float] | None:
    if len(samples) < 2:
        return None
    xs = [s.dac_v for s in samples]
    ys = [s.dds_amp for s in samples]
    mx = statistics.fmean(xs)
    my = statistics.fmean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx <= 1e-18:
        return None
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    intercept = my - slope * mx
    residuals = [y - (slope * x + intercept) for x, y in zip(xs, ys)]
    sse = sum(r * r for r in residuals)
    sst = sum((y - my) ** 2 for y in ys)
    return {
        "slope": slope,
        "intercept": intercept,
        "r2": 1.0 - sse / sst if sst > 1e-18 else float("nan"),
        "rmse": math.sqrt(sse / len(samples)),
        "x_span": max(xs) - min(xs),
        "y_span": max(ys) - min(ys),
    }


def percent_error(measured: float, expected: float) -> float:
    if abs(expected) < 1e-15:
        return 0.0 if abs(measured) < 1e-15 else float("inf")
    return abs((measured - expected) / expected) * 100.0


class RigolScope:
    def __init__(self, resource_name: str = "", timeout_ms: int = 5000) -> None:
        self.resource_name = resource_name.strip()
        self.timeout_ms = timeout_ms
        self.manager = None
        self.instrument = None
        self.identity = ""
        self.connected_resource = ""

    @staticmethod
    def _looks_like_rigol(identity: str) -> bool:
        folded = identity.casefold()
        return "rigol" in folded and "ds1102z-e" in folded

    def connect(self) -> str:
        try:
            import pyvisa
        except ImportError as exc:
            raise InstrumentError("没有安装 PyVISA。请运行安装依赖.cmd。") from exc
        try:
            manager = pyvisa.ResourceManager()
        except Exception as exc:
            raise InstrumentError(f"无法启动 VISA：{exc}") from exc

        resources = (self.resource_name,) if self.resource_name else tuple(manager.list_resources())
        if not resources:
            manager.close()
            raise InstrumentError("VISA 没有发现仪器。请检查示波器 USB Device/LAN 连接。")

        observations: list[str] = []
        selected = None
        for resource in resources:
            parts = str(resource).split("::")
            if not self.resource_name and len(parts) >= 2 and parts[0].upper().startswith("USB"):
                try:
                    vendor = int(parts[1], 0)
                except ValueError:
                    vendor = None
                if vendor is not None and vendor != 0x1AB1:
                    continue
            candidate = None
            try:
                candidate = manager.open_resource(resource)
                candidate.timeout = self.timeout_ms
                if hasattr(candidate, "read_termination"):
                    candidate.read_termination = "\n"
                if hasattr(candidate, "write_termination"):
                    candidate.write_termination = "\n"
                identity = str(candidate.query("*IDN?")).strip()
                observations.append(f"{resource} -> {identity}")
                if self._looks_like_rigol(identity):
                    selected = candidate
                    self.identity = identity
                    self.connected_resource = str(resource)
                    break
            except Exception as exc:
                observations.append(f"{resource} -> {exc}")
            if candidate is not None and candidate is not selected:
                try:
                    candidate.close()
                except Exception:
                    pass

        if selected is None:
            manager.close()
            detail = "\n".join(observations) or "未查询到可用资源"
            raise InstrumentError(f"没有找到 RIGOL DS1102Z-E：\n{detail}")

        self.manager = manager
        self.instrument = selected
        self.check_channels()
        return f"{self.identity} | {self.connected_resource}"

    def check_channels(self) -> None:
        if self.instrument is None:
            raise InstrumentError("示波器尚未连接")
        for channel in (1, 2):
            if str(self.instrument.query(f":CHANnel{channel}:DISPlay?")).strip() != "1":
                raise InstrumentError(f"请先在示波器上打开 CH{channel}")

    def _query_measurement(self, item: str, channel: int) -> float:
        assert self.instrument is not None
        return finite_number(self.instrument.query(f":MEASure:ITEM? {item},CHANnel{channel}"))

    def read_same_frame(self, stop_event: threading.Event, amp_item: str = "VPP") -> tuple[float, float, float] | None:
        if self.instrument is None:
            raise InstrumentError("示波器尚未连接")
        scope = self.instrument
        scope.write(":RUN")
        if stop_event.wait(0.08):
            return None
        scope.write(":SINGle")
        if stop_event.wait(0.08):
            return None
        scope.write(":TFORce")

        deadline = time.monotonic() + 4.0
        while str(scope.query(":TRIGger:STATus?")).strip().upper() != "STOP":
            if stop_event.wait(0.01):
                return None
            if time.monotonic() > deadline:
                raise InstrumentError("等待示波器冻结新帧超时；本次没有使用旧数据")

        dac_v = self._query_measurement("VAVG", 1)
        dds_amp = self._query_measurement(amp_item, 2)
        freq_hz = self._query_measurement("FREQuency", 2)
        if str(scope.query(":TRIGger:STATus?")).strip().upper() != "STOP":
            raise InstrumentError("读取期间示波器被重新启动，本次三项数据已丢弃")
        if amp_item in {"VPP", "VRMS"} and dds_amp < 0:
            raise InstrumentError(f"CH2 返回负幅度：{dds_amp}")
        return dac_v, dds_amp, freq_hz / 1e6

    def resume(self) -> None:
        if self.instrument is not None:
            try:
                self.instrument.write(":TRIGger:SWEep AUTO")
                self.instrument.write(":RUN")
            except Exception:
                pass

    def close(self) -> None:
        self.resume()
        instrument, self.instrument = self.instrument, None
        manager, self.manager = self.manager, None
        if instrument is not None:
            try:
                instrument.close()
            except Exception:
                pass
        if manager is not None:
            try:
                manager.close()
            except Exception:
                pass


class Application:
    BG = "#0f1720"
    PANEL = "#17232f"
    TEXT = "#e7edf3"
    MUTED = "#98a8b7"
    CYAN = "#31c7bd"
    ORANGE = "#f0a34a"
    RED = "#ef6b73"
    GRID = "#2a3a48"

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("DAC → DDS 同帧测试")
        self.root.geometry("980x680")
        self.root.minsize(820, 560)
        self.root.configure(bg=self.BG)

        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.stop_event = threading.Event()
        self.scope: RigolScope | None = None
        self.worker: threading.Thread | None = None
        self.samples: list[Sample] = []
        self.started_at = 0.0

        self.resource_var = tk.StringVar()
        self.k_var = tk.StringVar(value="0.04")
        self.b_var = tk.StringVar(value="0.30")
        self.interval_var = tk.StringVar(value="0.20")
        self.tolerance_var = tk.StringVar(value="5")
        self.amp_item_var = tk.StringVar(value="VPP")
        self.status_var = tk.StringVar(value="未连接：CH1 接 DAC，CH2 接 DDS RF")
        self.result_var = tk.StringVar(value="等待数据")
        self.live_var = tk.StringVar(value="当前：尚无数据")
        self.table: ttk.Treeview | None = None

        self._build_style()
        self._build_ui()
        self.root.after(50, self._poll_events)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_style(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background=self.BG)
        style.configure("Panel.TFrame", background=self.PANEL)
        style.configure("TLabel", background=self.BG, foreground=self.TEXT, font=("Microsoft YaHei UI", 10))
        style.configure("Panel.TLabel", background=self.PANEL, foreground=self.TEXT, font=("Microsoft YaHei UI", 10))
        style.configure("Muted.TLabel", background=self.PANEL, foreground=self.MUTED, font=("Microsoft YaHei UI", 9))
        style.configure("Title.TLabel", background=self.BG, foreground=self.TEXT, font=("Microsoft YaHei UI", 20, "bold"))
        style.configure("Result.TLabel", background=self.PANEL, foreground=self.CYAN, font=("Consolas", 12, "bold"))
        style.configure("TButton", font=("Microsoft YaHei UI", 10), padding=(12, 8))
        style.configure("Accent.TButton", background=self.CYAN, foreground="#071014")
        style.map("Accent.TButton", background=[("active", "#49ddd2"), ("disabled", "#496d70")])
        style.configure("Treeview", background="#101a23", fieldbackground="#101a23", foreground=self.TEXT, rowheight=25, borderwidth=0)
        style.configure("Treeview.Heading", background="#243442", foreground=self.TEXT, font=("Microsoft YaHei UI", 9, "bold"))
        style.map("Treeview", background=[("selected", "#245b63")])

    def _entry(self, parent: tk.Widget, text: str, variable: tk.StringVar, width: int = 10) -> ttk.Frame:
        frame = ttk.Frame(parent, style="Panel.TFrame")
        ttk.Label(frame, text=text, style="Muted.TLabel").pack(anchor="w")
        ttk.Entry(frame, textvariable=variable, width=width).pack(fill="x", pady=(4, 0))
        return frame

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=16)
        outer.pack(fill="both", expand=True)
        header = ttk.Frame(outer)
        header.pack(fill="x")
        ttk.Label(header, text="DAC → DDS 同帧测试", style="Title.TLabel").pack(side="left")
        ttk.Button(header, text="高级设置", command=self._show_advanced).pack(side="right")
        ttk.Label(outer, text="CH1 测 DAC 电压，CH2 测 DDS RF；每个点来自同一个冻结帧", foreground=self.MUTED).pack(anchor="w", pady=(3, 12))

        control = ttk.Frame(outer, style="Panel.TFrame", padding=12)
        control.pack(fill="x")
        control.columnconfigure(2, weight=1)
        self._entry(control, "目标斜率 k", self.k_var, 12).grid(row=0, column=0, padx=(0, 8))
        self._entry(control, "目标截距 b", self.b_var, 12).grid(row=0, column=1, padx=8)
        ttk.Label(control, text="确认目标函数后，连接并开始", style="Muted.TLabel").grid(row=0, column=2, padx=16)

        buttons = ttk.Frame(control, style="Panel.TFrame")
        buttons.grid(row=0, column=3, padx=(12, 0), sticky="e")
        self.connect_button = ttk.Button(buttons, text="连接", command=self._connect)
        self.connect_button.grid(row=0, column=0, padx=3)
        self.start_button = ttk.Button(buttons, text="开始", style="Accent.TButton", command=self._start, state="disabled")
        self.start_button.grid(row=0, column=1, padx=3)
        self.stop_button = ttk.Button(buttons, text="停止", command=self._stop, state="disabled")
        self.stop_button.grid(row=0, column=2, padx=3)

        status = ttk.Frame(outer, style="Panel.TFrame", padding=(12, 8))
        status.pack(fill="x", pady=10)
        ttk.Label(status, textvariable=self.status_var, style="Panel.TLabel").pack(anchor="w")
        ttk.Label(status, textvariable=self.live_var, style="Muted.TLabel").pack(anchor="w", pady=(5, 0))
        ttk.Label(status, textvariable=self.result_var, style="Result.TLabel", wraplength=900).pack(anchor="w", pady=(5, 0))

        graph_panel = ttk.Frame(outer, style="Panel.TFrame", padding=8)
        graph_panel.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(graph_panel, bg="#0b131b", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _event: self._draw_plot())

        footer = ttk.Frame(outer)
        footer.pack(fill="x", pady=(8, 0))
        ttk.Label(footer, text="示波器上先调好 CH1/CH2 量程、时基和触发", foreground=self.MUTED).pack(side="left")
        ttk.Button(footer, text="清空", command=self._clear).pack(side="right", padx=(6, 0))
        ttk.Button(footer, text="导出 CSV", command=self._export).pack(side="right")

    def _show_advanced(self) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("高级设置")
        dialog.transient(self.root)
        dialog.resizable(False, False)
        dialog.configure(bg=self.BG)
        panel = ttk.Frame(dialog, style="Panel.TFrame", padding=16)
        panel.pack(fill="both", expand=True, padx=12, pady=12)
        self._entry(panel, "VISA 资源（留空自动找 RIGOL）", self.resource_var, 38).grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        self._entry(panel, "采样间隔 / s", self.interval_var, 14).grid(row=1, column=0, padx=(0, 8))
        self._entry(panel, "k、b 容差 / %", self.tolerance_var, 14).grid(row=1, column=1, padx=(8, 0))
        metric = ttk.Frame(panel, style="Panel.TFrame")
        metric.grid(row=2, column=0, sticky="w", pady=(12, 0))
        ttk.Label(metric, text="CH2 幅度口径", style="Muted.TLabel").pack(anchor="w")
        ttk.Combobox(metric, textvariable=self.amp_item_var, values=("VPP", "VRMS"), state="readonly", width=12).pack(pady=(4, 0))
        ttk.Button(panel, text="关闭", command=dialog.destroy).grid(row=2, column=1, sticky="se", pady=(12, 0))

    def _number(self, variable: tk.StringVar, name: str, *, minimum: float | None = None) -> float:
        try:
            value = float(variable.get())
        except ValueError as exc:
            raise ValueError(f"{name}不是数字") from exc
        if not math.isfinite(value) or minimum is not None and value < minimum:
            raise ValueError(f"{name}必须 ≥ {minimum}")
        return value

    def _connect(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        self.connect_button.configure(state="disabled")
        self.status_var.set("正在连接 RIGOL DS1102Z-E…")

        def task() -> None:
            try:
                scope = RigolScope(self.resource_var.get())
                identity = scope.connect()
                self.events.put(("connected", (scope, identity)))
            except Exception as exc:
                self.events.put(("error", str(exc)))

        self.worker = threading.Thread(target=task, daemon=True)
        self.worker.start()

    def _start(self) -> None:
        if self.scope is None or self.worker and self.worker.is_alive():
            return
        try:
            k = self._number(self.k_var, "目标斜率 k")
            b = self._number(self.b_var, "目标截距 b")
            interval = self._number(self.interval_var, "采样间隔", minimum=0.05)
            self._number(self.tolerance_var, "容差", minimum=0)
        except ValueError as exc:
            messagebox.showerror("参数错误", str(exc), parent=self.root)
            return

        amp_item = self.amp_item_var.get()
        self.stop_event.clear()
        self.started_at = time.monotonic()
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.connect_button.configure(state="disabled")
        self.status_var.set("采集中：每个点先冻结同一帧，再读取 CH1/CH2")

        def task() -> None:
            assert self.scope is not None
            try:
                while not self.stop_event.is_set():
                    frame = self.scope.read_same_frame(self.stop_event, amp_item)
                    if frame is None:
                        break
                    dac_v, dds_amp, freq_mhz = frame
                    expected = k * dac_v + b
                    sample = Sample(
                        index=len(self.samples) + self.events.qsize() + 1,
                        timestamp=datetime.now().isoformat(timespec="milliseconds"),
                        elapsed_s=time.monotonic() - self.started_at,
                        dac_v=dac_v,
                        dds_amp=dds_amp,
                        freq_mhz=freq_mhz,
                        expected_amp=expected,
                        residual=dds_amp - expected,
                    )
                    self.events.put(("sample", sample))
                    if self.stop_event.wait(interval):
                        break
            except Exception as exc:
                self.events.put(("error", str(exc)))
            finally:
                self.scope.resume()
                self.events.put(("stopped", None))

        self.worker = threading.Thread(target=task, daemon=True)
        self.worker.start()

    def _stop(self) -> None:
        self.stop_event.set()
        self.stop_button.configure(state="disabled")
        self.status_var.set("正在停止；等待当前 VISA 操作返回…")

    def _clear(self) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showwarning("正在采集", "请先停止采集。", parent=self.root)
            return
        if self.samples and not messagebox.askyesno("清空", "确定清空当前全部数据？", parent=self.root):
            return
        self.samples.clear()
        if self.table is not None:
            for item in self.table.get_children():
                self.table.delete(item)
        self.result_var.set("等待数据")
        self.live_var.set("当前：尚无数据")
        self._draw_plot()

    def _export(self) -> None:
        if not self.samples:
            messagebox.showinfo("没有数据", "先采集数据再导出。", parent=self.root)
            return
        default = f"dds_dac_same_frame_{datetime.now():%Y%m%d_%H%M%S}.csv"
        filename = filedialog.asksaveasfilename(parent=self.root, title="导出 CSV", defaultextension=".csv", initialfile=default, filetypes=[("CSV", "*.csv")])
        if not filename:
            return
        fit = linear_fit(self.samples)
        with open(filename, "w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(["target_slope", self.k_var.get(), "target_intercept", self.b_var.get(), "CH2_item", self.amp_item_var.get()])
            if fit:
                writer.writerow(["fit_slope", fit["slope"], "fit_intercept", fit["intercept"], "R2", fit["r2"], "RMSE", fit["rmse"]])
            writer.writerow(["index", "timestamp", "elapsed_s", "dac_ch1_vavg_V", f"dds_ch2_{self.amp_item_var.get()}", "dds_frequency_MHz", "expected", "residual"])
            for s in self.samples:
                writer.writerow([s.index, s.timestamp, f"{s.elapsed_s:.6f}", f"{s.dac_v:.9g}", f"{s.dds_amp:.9g}", f"{s.freq_mhz:.9g}", f"{s.expected_amp:.9g}", f"{s.residual:.9g}"])
        self.status_var.set(f"已导出：{filename}")

    def _poll_events(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "connected":
                    self.scope, identity = payload  # type: ignore[misc]
                    self.status_var.set(f"已连接：{identity}")
                    self.connect_button.configure(state="disabled")
                    self.start_button.configure(state="normal")
                elif kind == "sample":
                    self._append_sample(payload)  # type: ignore[arg-type]
                elif kind == "error":
                    self.status_var.set(f"错误：{payload}")
                    messagebox.showerror("采集错误", str(payload), parent=self.root)
                    self.connect_button.configure(state="normal" if self.scope is None else "disabled")
                    self.start_button.configure(state="normal" if self.scope is not None else "disabled")
                    self.stop_button.configure(state="disabled")
                elif kind == "stopped":
                    self.stop_button.configure(state="disabled")
                    self.start_button.configure(state="normal" if self.scope is not None else "disabled")
                    if not self.status_var.get().startswith("错误"):
                        self.status_var.set(f"已停止，共 {len(self.samples)} 个同帧数据点")
        except queue.Empty:
            pass
        self.root.after(50, self._poll_events)

    def _append_sample(self, sample: Sample) -> None:
        sample = Sample(index=len(self.samples) + 1, timestamp=sample.timestamp, elapsed_s=sample.elapsed_s, dac_v=sample.dac_v, dds_amp=sample.dds_amp, freq_mhz=sample.freq_mhz, expected_amp=sample.expected_amp, residual=sample.residual)
        self.samples.append(sample)
        self.live_var.set(f"当前：DAC {sample.dac_v:.4f} V　DDS {sample.dds_amp:.4f} {self.amp_item_var.get()}　频率 {sample.freq_mhz:.4f} MHz　共 {sample.index} 点")
        if self.table is not None:
            self.table.insert("", "end", values=(sample.index, f"{sample.elapsed_s:.2f}", f"{sample.dac_v:.5f}", f"{sample.dds_amp:.5f}", f"{sample.freq_mhz:.4f}", f"{sample.expected_amp:.5f}", f"{sample.residual:+.5f}"))
            children = self.table.get_children()
            if children:
                self.table.see(children[-1])
        self._update_result()
        self._draw_plot()

    def _update_result(self) -> None:
        fit = linear_fit(self.samples)
        if fit is None:
            self.result_var.set(f"N={len(self.samples)}；等待电压跨度")
            return
        try:
            target_k = float(self.k_var.get())
            target_b = float(self.b_var.get())
            tolerance = float(self.tolerance_var.get())
        except ValueError:
            return
        k_error = percent_error(fit["slope"], target_k)
        b_error = percent_error(fit["intercept"], target_b)
        r2 = fit["r2"]
        passed = len(self.samples) >= 10 and math.isfinite(r2) and r2 >= 0.99 and k_error <= tolerance and b_error <= tolerance
        verdict = "一致" if passed else "未达到判据"
        gain_ratio = fit["slope"] / target_k if abs(target_k) > 1e-15 else math.nan
        self.result_var.set(f"{verdict}　实测 y={fit['slope']:.5g}x+{fit['intercept']:.5g}　R²={r2:.5f}　斜率倍率={gain_ratio:.3f}×")

    def _draw_plot(self) -> None:
        canvas = self.canvas
        canvas.delete("all")
        width = max(canvas.winfo_width(), 300)
        height = max(canvas.winfo_height(), 260)
        pad_l, pad_r, pad_t, pad_b = 64, 20, 24, 48
        if len(self.samples) < 2:
            canvas.create_text(width / 2, height / 2, text="开始采集后显示 DDS 幅度–DAC 电压关系", fill=self.MUTED, font=("Microsoft YaHei UI", 12))
            return
        xs = [s.dac_v for s in self.samples]
        ys = [s.dds_amp for s in self.samples]
        try:
            target_k = float(self.k_var.get())
            target_b = float(self.b_var.get())
        except ValueError:
            return
        x0, x1 = min(xs), max(xs)
        if x1 - x0 < 1e-12:
            x0 -= 1
            x1 += 1
        expected_ends = [target_k * x0 + target_b, target_k * x1 + target_b]
        y0, y1 = min(ys + expected_ends), max(ys + expected_ends)
        if y1 - y0 < 1e-12:
            y0 -= 1
            y1 += 1
        dx = (x1 - x0) * 0.08
        dy = (y1 - y0) * 0.10
        x0, x1, y0, y1 = x0 - dx, x1 + dx, y0 - dy, y1 + dy

        def sx(x: float) -> float:
            return pad_l + (x - x0) / (x1 - x0) * (width - pad_l - pad_r)

        def sy(y: float) -> float:
            return height - pad_b - (y - y0) / (y1 - y0) * (height - pad_t - pad_b)

        for i in range(6):
            gx = x0 + (x1 - x0) * i / 5
            gy = y0 + (y1 - y0) * i / 5
            canvas.create_line(sx(gx), pad_t, sx(gx), height - pad_b, fill=self.GRID)
            canvas.create_line(pad_l, sy(gy), width - pad_r, sy(gy), fill=self.GRID)
            canvas.create_text(sx(gx), height - 25, text=f"{gx:.2f}", fill=self.MUTED, font=("Consolas", 9))
            canvas.create_text(34, sy(gy), text=f"{gy:.3g}", fill=self.MUTED, font=("Consolas", 9))
        canvas.create_text(width / 2, height - 7, text="CH1 DAC 电压 / V", fill=self.TEXT)
        canvas.create_text(12, height / 2, text="CH2", angle=90, fill=self.TEXT)

        canvas.create_line(sx(x0), sy(target_k * x0 + target_b), sx(x1), sy(target_k * x1 + target_b), fill=self.CYAN, width=2)
        fit = linear_fit(self.samples)
        if fit:
            canvas.create_line(sx(x0), sy(fit["slope"] * x0 + fit["intercept"]), sx(x1), sy(fit["slope"] * x1 + fit["intercept"]), fill=self.ORANGE, width=2, dash=(7, 5))
        for sample in self.samples[-1500:]:
            x, y = sx(sample.dac_v), sy(sample.dds_amp)
            canvas.create_oval(x - 2.5, y - 2.5, x + 2.5, y + 2.5, fill="#d7edf0", outline="")
        canvas.create_text(pad_l + 5, pad_t + 5, text="青：目标直线　橙：实测拟合　白：同帧数据", anchor="nw", fill=self.MUTED, font=("Microsoft YaHei UI", 9))

    def _on_close(self) -> None:
        self.stop_event.set()
        if self.worker and self.worker.is_alive():
            self.worker.join(timeout=1.5)
        if self.scope is not None:
            self.scope.close()
        self.root.destroy()


def self_test() -> int:
    rows = []
    for i, x in enumerate((-5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 5), start=1):
        y = 0.04 * x + 0.30
        rows.append(Sample(i, "test", float(i), float(x), y, 100.0, y, 0.0))
    fit = linear_fit(rows)
    assert fit is not None
    assert abs(fit["slope"] - 0.04) < 1e-12
    assert abs(fit["intercept"] - 0.30) < 1e-12
    assert abs(fit["r2"] - 1.0) < 1e-12
    assert finite_number("100000000") == 100000000.0
    try:
        finite_number("9.9e37")
    except InstrumentError:
        pass
    else:
        raise AssertionError("invalid sentinel not rejected")
    print("SELF_TEST_PASS")
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    root = tk.Tk()
    Application(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
