```python
pip install ultralytics

from ultralytics import YOLO

# Load a COCO-pretrained YOLO12n model
model = YOLO("yolo12n.pt")

# Train the model on the COCO8 example dataset for 100 epochs
results = model.train(data="coco8.yaml", epochs=100, imgsz=640)

# Export the model
model.export(format="onnx")

# Run inference with the YOLO12n model on the 'bus.jpg' image
results = model("path/to/bus.jpg")
```

# YOLO 各版本对比与特点
如果您需要了解更多关于YOLO最新版本的详细信息，建议查阅[Ultralytics](https://www.ultralytics.com/zh)公司的[官方GitHub页面](https://github.com/ultralytics)或相关文献。
YOLO (You Only Look Once) 是目标检测领域最流行的模型系列之一，从最初版本到现在已经有了显著的发展。

[YOLOv12](https://docs.ultralytics.com/zh/models/yolo12/)

以下是YOLO各主要版本的对比与特点：

## YOLOv1 (2015)

- **创新点**：首次提出单阶段检测架构，将目标检测转化为回归问题
- **特点**：
  - 速度快（45 FPS），但准确率相对较低
  - 每个网格单元只预测两个边界框
  - 难以检测小目标和密集目标
- **网络结构**：基于GoogLeNet修改的24层卷积网络

## YOLOv2 / YOLO9000 (2016)

- **创新点**：引入了Darknet-19骨干网络和锚框(anchor boxes)
- **特点**：
  - 支持多尺度训练
  - 引入Batch Normalization
  - 预测9000类别物体的能力(YOLO9000)
  - 精度和速度平衡改善

## YOLOv3 (2018)

- **创新点**：引入了多尺度预测和更深的Darknet-53骨干网络
- **特点**：
  - 使用三种不同尺度的特征图进行预测
  - 每种尺度使用3个不同大小的锚框
  - 用于分类的二元交叉熵损失
  - 更好的小目标检测性能

## YOLOv4 (2020)

- **创新点**：集成了多种先进技术，如CSPDarknet53骨干网络、PANet特征融合
- **特点**：
  - 引入Mish激活函数
  - 使用CIOU损失函数
  - 数据增强：Mosaic和自适应锚框选择
  - 注意力机制：SPP、SAM等

## YOLOv5 (2020)

- **创新点**：由Ultralytics公司开发，不是原作者Joseph Redmon的工作
- **特点**：
  - PyTorch实现，易于使用和部署
  - 多种模型大小(nano, small, medium, large, xlarge)
  - 集成了AutoAnchor和超参数进化
  - 完善的训练、验证、推理和部署流程

## YOLOv6 (2022)

- **创新点**：由美团提出，专注于工业应用
- **特点**：
  - 重新设计的骨干网络和颈部网络
  - TAL (Task Alignment Learning)分配策略
  - 锚框无关的解码器
  - 量化感知训练支持

## YOLOv7 (2022)

- **创新点**：引入E-ELAN(扩展高效层聚合网络)架构
- **特点**：
  - 模型再参数化技术
  - 辅助头部训练策略
  - 动态标签分配
  - 在同等精度下速度更快

## YOLOv8 (2023)

- **创新点**：由Ultralytics开发，全面升级YOLOv5
- **特点**：
  - 采用锚框无关的检测头
  - C2f模块代替C3模块
  - 更高的分类和定位精度
  - 多任务支持：检测、分割、姿态估计等
  - 高效的代码库和API

## YOLO系列衍生版本

- **YOLOR (2021)**：融合显式和隐式知识，统一网络架构
- **PP-YOLO系列**：百度基于YOLOv3优化的版本，精度与速度均有提升
- **YOLOX (2021)**：解耦检测头，引入SimOTA动态标签分配
- **RT-DETR (2023)**：基于YOLO的实时检测Transformer模型
- **YOLOv9 (非官方/研究版本)**：有研究者提出的延续，但非官方主线版本

## YOLO模型的发展趋势主要集中在:
1. 提高检测精度的同时保持速度优势
2. 支持多任务学习（检测、分割、姿态估计等）
3. 更高效的网络架构设计
4. 更好的小目标检测能力
5. 部署优化和高效推理

# 使用YOLO进行实例分割任务的数据集准备

要使用YOLO（特别是YOLOv8或更高版本）进行实例分割任务，您需要准备一个适当标注的数据集。以下是详细的准备步骤：

## 数据集要求

对于实例分割任务，您需要：

1. **图像**：收集包含目标对象的图像
2. **多边形标注**：为每个目标对象创建精确的多边形轮廓（不仅仅是边界框）
3. **类别标签**：为每个分割的对象分配相应的类别

## 标注流程

### 1. 标注工具选择

以下是几个适合分割任务的标注工具：

- **[CVAT](https://www.cvat.ai/)**：功能强大的在线标注工具，支持多边形标注
- **Labelme**：简单易用的开源标注工具
- **Supervisely**：支持复杂分割任务的在线平台
- **Roboflow**：提供全流程标注和数据管理服务
- **VGG Image Annotator (VIA)**：轻量级标注工具

### 2. 标注过程

对于每张图像，您需要：

1. **绘制多边形**：围绕每个目标对象绘制精确的多边形轮廓
2. **分配类别**：为每个轮廓指定正确的类别标签
3. **确保完整性**：确保图像中所有需要识别的对象都被标注

### 3. 数据格式

YOLOv8原生支持COCO格式的实例分割标注。典型的YOLO实例分割标注格式为：

```
# 对于每张图像创建一个.txt文件
# 每行一个对象，格式为：
<class_id> <x1> <y1> <x2> <y2> ... <xn> <yn>
```

其中：
- `class_id`：对象的类别ID（整数，从0开始）
- `x1 y1 x2 y2 ... xn yn`：多边形顶点的归一化坐标（所有值在0-1范围内）

## 数据集组织

一个典型的YOLO实例分割数据集结构：

```
dataset/
├── images/
│   ├── train/
│   │   ├── image1.jpg
│   │   ├── image2.jpg
│   │   └── ...
│   ├── val/
│   │   ├── image1.jpg
│   │   └── ...
│   └── test/ (可选)
│       ├── image1.jpg
│       └── ...
├── labels/
│   ├── train/
│   │   ├── image1.txt
│   │   ├── image2.txt
│   │   └── ...
│   ├── val/
│   │   ├── image1.txt
│   │   └── ...
│   └── test/ (可选)
│       ├── image1.txt
│       └── ...
└── data.yaml
```

## data.yaml 文件示例

```yaml
path: ./dataset  # 数据集根目录
train: images/train  # 训练图像相对路径
val: images/val  # 验证图像相对路径
test: images/test  # 测试图像相对路径（可选）

# 类别名称
names:
  0: person
  1: car
  2: dog
  # 添加更多类别...
```

## 实用建议

1. **标注质量**：多边形应该尽可能准确地贴合对象边缘
2. **数据平衡**：每个类别应有足够数量的样本
3. **图像多样性**：包含不同光照、角度、大小的目标
4. **数据增强**：考虑在训练过程中使用数据增强（YOLOv8内置了许多增强选项）
5. **标注一致性**：确保相似对象的标注方式一致

## 使用YOLOv8进行训练

准备好数据集后，您可以使用以下命令训练YOLOv8模型进行实例分割：

```python
from ultralytics import YOLO

# 加载预训练模型
model = YOLO('yolov8n-seg.pt')  # 或其他尺寸的模型

# 训练模型
results = model.train(
    data='path/to/your/data.yaml',
    epochs=100,
    imgsz=640,
    batch=16,
    device=0  # 使用GPU
)
```

总结：实例分割任务确实需要为每个目标对象创建精确的多边形轮廓标注，并为每个对象分配相应的类别标签。这种标注比仅用于目标检测的边界框标注更加精确，但也更耗时。好的标注工具和清晰的数据组织将大大提高您的工作效率。
