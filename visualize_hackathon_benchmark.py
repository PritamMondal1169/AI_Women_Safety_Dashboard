import matplotlib.pyplot as plt
import numpy as np
import os

def create_benchmark_chart():
    # Data from latest stress tests
    labels = ['CPU (PyTorch)', 'RTX 3050 (TensorRT)']
    fps_data = [23.5, 117.1]
    latency_data = [42.5, 8.5]
    
    x = np.arange(len(labels))
    width = 0.35
    
    fig, ax1 = plt.subplots(figsize=(10, 6))
    
    # Plot FPS (Higher is better)
    color1 = '#00f2fe' # Neon blue
    bars1 = ax1.bar(x - width/2, fps_data, width, label='Throughput (FPS)', color=color1, edgecolor='white', linewidth=1.5)
    ax1.set_ylabel('Frames Per Second (FPS)', color=color1, fontsize=12, fontweight='bold')
    ax1.tick_params(axis='y', labelcolor=color1)
    
    # Plot Latency (Lower is better) - Secondary Y axis
    ax2 = ax1.twinx()
    color2 = '#ff0844' # Neon red
    bars2 = ax2.bar(x + width/2, latency_data, width, label='Latency (ms)', color=color2, edgecolor='white', linewidth=1.5)
    ax2.set_ylabel('Latency (milliseconds)', color=color2, fontsize=12, fontweight='bold')
    ax2.tick_params(axis='y', labelcolor=color2)
    
    # Text annotations
    for bar in bars1:
        height = bar.get_height()
        ax1.annotate(f"{height} FPS",
                     xy=(bar.get_x() + bar.get_width() / 2, height),
                     xytext=(0, 3), textcoords="offset points",
                     ha='center', va='bottom', color='white', fontweight='bold')
                     
    for bar in bars2:
        height = bar.get_height()
        ax2.annotate(f"{height} ms",
                     xy=(bar.get_x() + bar.get_width() / 2, height),
                     xytext=(0, 3), textcoords="offset points",
                     ha='center', va='bottom', color='white', fontweight='bold')
    
    # Styling and theme
    ax1.set_xticks(x)
    ax1.set_xticklabels(labels, fontsize=14, fontweight='bold', color='white')
    plt.title('Aegis Sentinel Inference Engine Benchmark\n(YOLOv8n-pose)', color='white', fontsize=16, fontweight='bold', pad=20)
    
    # Set dark theme look
    fig.patch.set_facecolor('#0f172a') # Tailwind slate-900
    ax1.set_facecolor('#0f172a')
    
    for spine in ax1.spines.values():
        spine.set_edgecolor('#334155')
    for spine in ax2.spines.values():
        spine.set_edgecolor('#334155')
    
    # Legends
    fig.legend(loc='upper left', bbox_to_anchor=(0.1, 0.9), facecolor='#1e293b', edgecolor='#334155', labelcolor='white')
    
    # Remove grid lines for a cleaner neon look or use very faint ones
    ax1.grid(True, linestyle='--', alpha=0.1, color='white')
    
    plt.tight_layout()
    output_path = os.path.join(os.path.dirname(__file__), 'hackathon_benchmark_chart.png')
    plt.savefig(output_path, dpi=300, facecolor=fig.get_facecolor(), edgecolor='none', bbox_inches='tight')
    print(f"Chart successfully generated and saved to: {output_path}")

if __name__ == "__main__":
    create_benchmark_chart()
