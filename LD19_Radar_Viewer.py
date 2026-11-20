import sys
import os
import time
import math
import struct
import threading
import tkinter as tk
from tkinter import ttk

try:
    import serial
except ImportError:
    print("pyserial is required.")
    sys.exit(1)

class RadarViewerApp:
    def __init__(self, root, port="COM7", baud=230400):
        self.root = root
        self.root.title("LD19 激光雷达 360° 实时点云监视器 (COM7)")
        self.root.geometry("860x900")
        self.root.configure(bg="#0a0e17")
        self.root.resizable(True, True)

        self.port_name = port
        self.baud_rate = baud
        self.max_range_m = 3.0  # 默认 3 米量程（完美适配 3m×2m 墙面互动）
        self.running = True
        
        # 点云存储（360度离散扇区缓存）
        self.point_buffer = {}  # angle_int -> (dist_mm, intensity, timestamp)
        self.lock = threading.Lock()
        self.pts_per_sec = 0
        self.scan_freq_hz = 10.0
        
        self.setup_ui()
        
        # 启动串口采集后台线程
        self.serial_thread = threading.Thread(target=self.serial_reader_worker, daemon=True)
        self.serial_thread.start()
        
        # 启动 UI 定时刷新循环 (约 30 FPS)
        self.update_canvas()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def setup_ui(self):
        # 顶部控制栏
        top_frame = tk.Frame(self.root, bg="#131b26", height=45)
        top_frame.pack(fill=tk.X, side=tk.TOP, padx=5, pady=5)

        title_lbl = tk.Label(top_frame, text="LD19 激光雷达实时点云", font=("微软雅黑", 12, "bold"), fg="#00e5ff", bg="#131b26")
        title_lbl.pack(side=tk.LEFT, padx=12, pady=6)

        # 测距量程切换
        range_lbl = tk.Label(top_frame, text="显示量程:", font=("微软雅黑", 10), fg="#a0aec0", bg="#131b26")
        range_lbl.pack(side=tk.LEFT, padx=5)

        for r in [1.0, 2.0, 3.0, 5.0, 8.0]:
            btn = tk.Button(top_frame, text=f"{int(r) if r.is_integer() else r}m", font=("微软雅黑", 9),
                            bg="#1e293b", fg="#ffffff", activebackground="#00e5ff", activeforeground="#000000",
                            relief=tk.FLAT, padx=6, command=lambda val=r: self.set_range(val))
            btn.pack(side=tk.LEFT, padx=3)

        self.fps_lbl = tk.Label(top_frame, text="点数: 0 pts/s", font=("Consolas", 10), fg="#48bb78", bg="#131b26")
        self.fps_lbl.pack(side=tk.RIGHT, padx=15)

        # 画布区域
        self.canvas = tk.Canvas(self.root, bg="#070b12", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)
        self.canvas.bind("<Configure>", lambda e: self.redraw_background())
        self.canvas.bind("<Motion>", self.on_mouse_move)

        # 底部状态栏
        self.status_bar = tk.Label(self.root, text=f"端口: {self.port_name} | 波特率: {self.baud_rate} | 状态: 采集中... | 坐标: -",
                                   font=("微软雅黑", 9), fg="#718096", bg="#0a0e17", anchor="w")
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM, padx=10, pady=4)

    def set_range(self, val):
        self.max_range_m = val

    def redraw_background(self):
        pass  # 动态计算在 update_canvas 绘制

    def on_mouse_move(self, event):
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        cx, cy = w / 2, h / 2
        dx = (event.x - cx)
        dy = (cy - event.y)
        dist_px = math.sqrt(dx*dx + dy*dy)
        scale = (min(cx, cy) * 0.90) / self.max_range_m
        dist_m = dist_px / scale if scale > 0 else 0
        deg = (math.degrees(math.atan2(dx, dy)) + 360) % 360
        self.status_bar.config(text=f"端口: {self.port_name} (230400) | 鼠标距离雷达中心: {dist_m:.2f} m | 角度: {deg:.1f}°")

    def serial_reader_worker(self):
        try:
            ser = serial.Serial(self.port_name, self.baud_rate, timeout=1)
        except Exception as e:
            self.status_bar.config(text=f"无法打开端口 {self.port_name}: {e}")
            return

        cnt = 0
        t0 = time.time()

        while self.running:
            try:
                b = ser.read(1)
                if b == b'\x54':
                    b2 = ser.read(1)
                    if b2 == b'\x2c':
                        data = ser.read(45)
                        if len(data) == 45:
                            speed, start_angle = struct.unpack('<HH', data[0:4])
                            end_angle = struct.unpack('<H', data[36:38])[0]
                            start_deg = start_angle / 100.0
                            end_deg = end_angle / 100.0
                            if end_deg < start_deg:
                                end_deg += 360.0
                            step = (end_deg - start_deg) / 11.0
                            
                            now = time.time()
                            with self.lock:
                                for i in range(12):
                                    dist_mm, intensity = struct.unpack('<HB', data[4 + i*3 : 7 + i*3])
                                    deg = (start_deg + step * i) % 360.0
                                    # 将 360 度划分为 720 个半度桶
                                    bucket = int(deg * 2) % 720
                                    if dist_mm > 20:  # 过滤盲区 (<2cm)
                                        self.point_buffer[bucket] = (deg, dist_mm, intensity, now)
                                        cnt += 1
                                        
                            if time.time() - t0 >= 1.0:
                                self.pts_per_sec = cnt
                                cnt = 0
                                t0 = time.time()
            except Exception as e:
                time.sleep(0.01)

        ser.close()

    def update_canvas(self):
        if not self.running:
            return

        self.canvas.delete("all")
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w < 100 or h < 100:
            self.root.after(30, self.update_canvas)
            return

        cx, cy = w / 2, h / 2
        radius = min(cx, cy) * 0.88
        scale = radius / self.max_range_m

        # 1. 绘制网格同心圆
        rings = [0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 8.0]
        for rm in rings:
            if rm <= self.max_range_m:
                r_px = rm * scale
                self.canvas.create_oval(cx - r_px, cy - r_px, cx + r_px, cy + r_px,
                                        outline="#162536", width=1, dash=(3, 3))
                self.canvas.create_text(cx + 8, cy - r_px - 8, text=f"{rm}m",
                                        fill="#3b536f", font=("Consolas", 8))

        # 2. 绘制十字刻度线与角度标
        self.canvas.create_line(cx - radius, cy, cx + radius, cy, fill="#1c2f42", width=1)
        self.canvas.create_line(cx, cy - radius, cx, cy + radius, fill="#1c2f42", width=1)
        
        self.canvas.create_text(cx, cy - radius - 12, text="0° (正前方)", fill="#00e5ff", font=("微软雅黑", 9, "bold"))
        self.canvas.create_text(cx + radius + 25, cy, text="90° (右)", fill="#718096", font=("微软雅黑", 8))
        self.canvas.create_text(cx, cy + radius + 12, text="180° (后方)", fill="#718096", font=("微软雅黑", 8))
        self.canvas.create_text(cx - radius - 25, cy, text="270° (左)", fill="#718096", font=("微软雅黑", 8))

        # 3. 如果在 3m 互动量程下，标出 3m×2m 虚拟墙面交互框（示意参考）
        if self.max_range_m >= 3.0:
            box_w = 3.0 * scale
            box_h = 2.0 * scale
            # 假设雷达在墙顶正中 (cx, cy) 向下扫墙面
            self.canvas.create_rectangle(cx - box_w/2, cy, cx + box_w/2, cy + box_h,
                                         outline="#ffb703", width=1, dash=(5, 5))
            self.canvas.create_text(cx - box_w/2 + 65, cy + 12, text="3m×2m 墙面互动区范围",
                                    fill="#ffb703", font=("微软雅黑", 8))

        # 4. 绘制实时扫描点云
        now = time.time()
        with self.lock:
            # 清理 0.35 秒前的过期点（保证残影消失，反映真实移动）
            expired_keys = [k for k, v in self.point_buffer.items() if (now - v[3]) > 0.35]
            for k in expired_keys:
                del self.point_buffer[k]

            active_points = list(self.point_buffer.values())

        for pt in active_points:
            deg, dist_mm, intensity, t = pt
            dist_m = dist_mm / 1000.0
            if dist_m > self.max_range_m:
                continue

            # 角度换算：0度为上方正前方，顺时针旋转
            rad = math.radians(deg)
            px = cx + (dist_m * scale) * math.sin(rad)
            py = cy - (dist_m * scale) * math.cos(rad)

            # 根据反射强度映射颜色（弱反射偏青绿，强反射亮金黄）
            if intensity > 150:
                color = "#ffe600"
                r = 2.5
            elif intensity > 80:
                color = "#00ffcc"
                r = 2.0
            else:
                color = "#00a884"
                r = 1.5

            self.canvas.create_oval(px - r, py - r, px + r, py + r, fill=color, outline="")

        # 5. 绘制雷达中心圆点
        self.canvas.create_oval(cx - 5, cy - 5, cx + 5, cy + 5, fill="#ff0055", outline="#ffffff", width=1)
        self.canvas.create_text(cx, cy + 14, text="LD19 雷达中心", fill="#ff0055", font=("微软雅黑", 8))

        # 更新帧率与点云密度显示
        self.fps_lbl.config(text=f"有效点频: {self.pts_per_sec} pts/s | 活跃点数: {len(active_points)}")

        # 下一帧刷新 (约 33ms ➔ 30 FPS)
        self.root.after(33, self.update_canvas)

    def on_close(self):
        self.running = False
        time.sleep(0.1)
        self.root.destroy()

if __name__ == "__main__":
    port = "COM7"
    if len(sys.argv) > 1:
        port = sys.argv[1]
    root = tk.Tk()
    app = RadarViewerApp(root, port=port)
    root.mainloop()
