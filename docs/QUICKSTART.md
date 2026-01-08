# 智能健康监测镜 - 快速入门指南

## 一、硬件连接

### GPIO 引脚连接（BCM编号）
```
LED 模块:
- 红色 LED  → GPIO 17
- 绿色 LED  → GPIO 27
- 蓝色 LED  → GPIO 22
- GND      → Ground

按钮模块:
- 按钮信号  → GPIO 23
- GND      → Ground

摄像头:
- 连接到 Camera接口

麦克风/扬声器:
- 通过 USB 或 3.5mm 接口连接
```

## 二、软件安装

### 1. 克隆项目
```bash
cd ~
git clone <your-repo-url> health_mirror
cd health_mirror
```

### 2. 运行安装脚本
```bash
chmod +x install.sh
./install.sh
```

### 3. 配置 API 密钥
编辑 `config.yaml`，填入你的 Porcupine API 密钥：
```bash
nano config.yaml
# 修改 audio.porcupine.access_key
```

## 三、测试

### 硬件测试
```bash
python3 main.py --test-hardware
```
应该看到 LED 依次点亮：绿色 → 黄色 → 红色 → 呼吸效果

### 音频测试
```bash
python3 main.py --test-audio
```
应该听到语音："Hello, I am your smart health monitoring mirror."

## 四、运行系统

### 启动主程序
```bash
python3 main.py
```

### 系统会依次：
1. 初始化硬件（绿色 LED 亮起）
2. 加载 AI 模型
3. 启动摄像头
4. 开始语音监听
5. 播报："System ready. Monitoring started."

## 五、使用方法

### 语音交互
1. 说出唤醒词："Hey Mirror"
2. LED 闪烁黄色表示正在监听
3. 说出命令：
   - "What's my status?" - 查询当前状态
   - "I'm okay" - 解除疲劳警报
   - "Set timer" - 设置休息提醒（开发中）
   - "Stop monitoring" - 暂停监测

### 按钮交互
- **单击**：快速检查状态 / 确认警报
- **双击**：播报当前状态
- **长按（3秒）**：切换监测模式
- **超长按（10秒）**：系统关机

### LED 状态指示
- **绿色常亮**：正常状态
- **黄色闪烁**：正在监听语音
- **黄色常亮**：轻度疲劳警告
- **红色呼吸**：严重疲劳警告

## 六、故障排查

### 摄像头无法打开
```bash
# 检查摄像头是否启用
sudo raspi-config
# Interface Options → Camera → Enable

# 测试摄像头
raspistill -o test.jpg
```

### 语音识别不工作
```bash
# 检查麦克风
arecord -l

# 测试录音
arecord -d 3 test.wav
aplay test.wav
```

### 导入错误
```bash
# 重新安装依赖
pip3 install -r requirements.txt --force-reinstall
```

### GPIO 权限错误
```bash
# 添加用户到 GPIO 组
sudo usermod -a -G gpio $USER
# 重新登录
```

## 七、开机自启动（可选）

### 创建 systemd 服务
```bash
sudo nano /etc/systemd/system/health-mirror.service
```

内容：
```ini
[Unit]
Description=Smart Health Monitoring Mirror
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/health_mirror
ExecStart=/usr/bin/python3 /home/pi/health_mirror/main.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

启用服务：
```bash
sudo systemctl daemon-reload
sudo systemctl enable health-mirror.service
sudo systemctl start health-mirror.service

# 查看状态
sudo systemctl status health-mirror.service
```

## 八、日志查看

### 实时日志
```bash
tail -f logs/main.log
tail -f logs/vision_service.log
tail -f logs/audio_service.log
```

### systemd 日志（如果使用服务）
```bash
sudo journalctl -u health-mirror.service -f
```

## 九、常见问题

**Q: 系统运行缓慢？**
A: 降低 `config.yaml` 中的 `vision.fps` 参数，或增加 `frame_skip`。

**Q: 误报频繁？**
A: 调整 `fatigue_thresholds` 中的阈值，增大 `ear_threshold` 或 `perclos_window`。

**Q: 语音唤醒不灵敏？**
A: 调整 `porcupine.sensitivity` 参数（0.0-1.0），数值越大越灵敏。

**Q: LED 颜色不对？**
A: 检查 GPIO 接线，确认 `config.yaml` 中的引脚配置正确。

## 十、进一步开发

### 修改疲劳检测阈值
编辑 `config.yaml` → `vision.fatigue_thresholds`

### 添加新的语音命令
编辑 `main.py` → `_process_command()` 方法

### 自定义 LED 效果
编辑 `modules/hardware_io.py` → 添加新的 LED 方法

### 添加新的警报级别
编辑 `config.yaml` → `alerts.levels`

## 支持
如遇问题，请查看日志文件或提交 Issue。
