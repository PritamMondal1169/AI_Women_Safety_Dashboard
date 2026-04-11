import matplotlib.pyplot as plt
import numpy as np

# Data
labels = ['CPU Baseline', 'PyTorch FP16 (CUDA)', 'TensorRT (.engine)']
latency = [42.48, 39.47, 24.86]
fps = [23.54, 25.34, 40.23]

x = np.arange(len(labels))
width = 0.4

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

# Plot Latency
rects1_1 = ax1.bar(x, latency, width, color=['#3498db', '#e74c3c', '#9b59b6'], edgecolor='black')
ax1.set_ylabel('Latency (ms) - Lower is Better', fontweight='bold')
ax1.set_title('Inference Latency Comparison', fontweight='bold', pad=15)
ax1.set_xticks(x)
ax1.set_xticklabels(labels, fontweight='bold')
ax1.set_ylim(0, max(latency) * 1.2)
for i, v in enumerate(latency):
    ax1.text(i, v + 1, f"{v} ms", ha='center', va='bottom', fontsize=12, fontweight='bold')

# Plot FPS
rects2_1 = ax2.bar(x, fps, width, color=['#2ecc71', '#f39c12', '#1abc9c'], edgecolor='black')
ax2.set_ylabel('Frames Per Second (FPS) - Higher is Better', fontweight='bold')
ax2.set_title('Throughput Performance Comparison', fontweight='bold', pad=15)
ax2.set_xticks(x)
ax2.set_xticklabels(labels, fontweight='bold')
ax2.set_ylim(0, max(fps) * 1.2)
for i, v in enumerate(fps):
    ax2.text(i, v + 1, f"{v} FPS", ha='center', va='bottom', fontsize=12, fontweight='bold')

plt.suptitle("PyTorch vs TensorRT YOLOv8n-pose Benchmark", fontsize=16, fontweight='bold', y=1.05)
plt.tight_layout()

# Add a subtle grid
ax1.grid(axis='y', linestyle='--', alpha=0.7)
ax2.grid(axis='y', linestyle='--', alpha=0.7)

# Save
output_path = "benchmark_results_trt.png"
plt.savefig(output_path, bbox_inches='tight', dpi=150)
print(f"Saved benchmark visualization to {output_path}")
