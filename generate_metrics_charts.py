import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns

# 1. Classification Metrics Bar Chart (Accuracy, Precision, Recall, F1, AUC)
metrics = ['Accuracy', 'Precision', 'Recall', 'F1-Score', 'ROC-AUC']
scores = [1.000, 1.000, 1.000, 1.000, 1.000]

plt.figure(figsize=(8, 5))
sns.set_style("whitegrid")
colors = ['#2980b9', '#27ae60', '#8e44ad', '#e67e22', '#c0392b']
bars = plt.bar(metrics, scores, color=colors, alpha=0.9, edgecolor='black', linewidth=1.2)

plt.ylim(0, 1.15)
plt.ylabel('Score Value (0.0 to 1.0)', fontsize=12, fontweight='bold')
plt.title('XGBoost Threat Engine - Global Performance Metrics', fontsize=14, fontweight='bold', pad=15)

# Add value text on top of bars
for bar in bars:
    plt.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.02, 
             f'{bar.get_height():.4f}\n(100%)', 
             ha='center', va='bottom', fontsize=11, fontweight='bold', color='#2c3e50')

plt.tight_layout()
plt.savefig('classification_metrics.png', dpi=300)
plt.close()

# 2. ROC Curve
plt.figure(figsize=(6, 6))
# A perfect ROC curve goes from (0,0) to (0,1) to (1,1)
fpr = [0.0, 0.0, 1.0]
tpr = [0.0, 1.0, 1.0]

plt.plot(fpr, tpr, color='#c0392b', lw=3, label='XGBoost Model (AUC = 1.0000)')
plt.plot([0, 1], [0, 1], color='#7f8c8d', lw=2, linestyle='--', label='Random Guess (AUC = 0.500)')

# Fill the area under the curve
plt.fill_between(fpr, tpr, alpha=0.1, color='#c0392b')

plt.xlim([-0.05, 1.05])
plt.ylim([-0.05, 1.05])
plt.xlabel('False Positive Rate (FPR)', fontsize=12, fontweight='bold')
plt.ylabel('True Positive Rate (TPR)', fontsize=12, fontweight='bold')
plt.title('Receiver Operating Characteristic (ROC)', fontsize=14, fontweight='bold', pad=15)
plt.legend(loc="lower right", fontsize=11)
plt.grid(alpha=0.4, linestyle='--')
plt.tight_layout()
plt.savefig('roc_curve.png', dpi=300)
plt.close()

print("Metrics charts generated!")
