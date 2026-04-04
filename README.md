A fully virtualized multi-agent reinforcement learning (MARL) system that teaches 
ESP32 edge nodes to make smart caching decisions in real time.

The control plane runs a Liquid Neural Network (LNN) Actor trained by a Twin Delayed 
DDPG (TD3) Critic. Simulated ESP32 nodes (via Wokwi + PlatformIO) communicate with 
the AI controller over MQTT, learning to cache smart grid power data without ever 
touching physical hardware.

Built with: Python · PyTorch · ncps · PlatformIO · Wokwi · Docker · Eclipse Mosquitto
