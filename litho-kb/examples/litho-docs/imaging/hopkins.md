# Hopkins 部分相干成像

Hopkins 公式是计算光刻中描述部分相干照明成像的标准模型。它把照明光源和投影光瞳合并为传输交叉系数（TCC），从而使空间像计算只依赖于掩模频谱。

## TCC 分解

TCC 是一个四维核函数，直接计算代价很高。常见做法是对 TCC 做特征值分解，得到 SOCS（Sum of Coherent Systems）核。

$$ I(x) = \sum_k \lambda_k |(\phi_k * M)(x)|^2 $$

截断前若干个特征值最大的核即可在精度与速度之间取得平衡，典型做法保留 10 到 30 个核。

![SOCS 示意图](socs.svg)

## 局限

Hopkins 模型假设掩模是薄掩模（Kirchhoff 近似）。在 EUV 和高 NA 条件下，掩模三维效应显著，需要引入 M3D 模型修正。

返回 [成像模型](README.md)。
