# 智能健康监测镜 (Smart Health Monitoring Mirror)

## 项目简介
基于树莓派Zero 2W的智能健康监测系统，通过摄像头实时检测用户疲劳状态，结合语音交互提供健康提醒。

## 硬件配置
- 树莓派 Zero 2W
- 摄像头模块
- 麦克风模块
- 扬声器模块
- 按钮模块
- LED灯模块（RGB三色）

## 核心功能
1. **疲劳检测**：基于EAR/MAR算法实时分析面部特征
2. **语音交互**：支持唤醒词和自然语言命令
3. **多级警报**：绿色(正常)/黄色(轻度疲劳)/红色(严重疲劳)
4. **边缘计算**：所有处理在本地完成，保护隐私

## 技术架构
- **视觉服务**：OpenCV + dlib
- **音频服务**：Porcupine (唤醒词) + Vosk (ASR) + PicoTTS (TTS)
- **IPC通信**：ZeroMQ
- **硬件控制**：RPi.GPIO

## 快速开始
```bash
# 安装依赖
pip install -r requirements.txt

# 下载模型文件
./scripts/download_models.sh

# 运行系统
python main.py
```

## 项目结构
```
.
├── main.py                 # 主程序入口
├── config.yaml            # 配置文件
├── modules/               # 核心模块
│   ├── vision_service.py
│   ├── audio_service.py
│   ├── alert_manager.py
│   └── hardware_io.py
├── utils/                 # 工具模块
│   ├── ipc.py
│   ├── logger.py
│   └── watchdog.py
├── models/                # AI模型文件
└── logs/                  # 运行日志
```

## 开发团队
毕业设计项目 - 机电专业

## 许可证
MIT License
