# Hopkins partially coherent imaging

The Hopkins formulation is the standard model for imaging under partially coherent illumination in computational lithography. It combines the illumination source and the projection pupil into the transmission cross coefficient (TCC), so that aerial image computation depends only on the mask spectrum.

## TCC decomposition

The TCC is a four-dimensional kernel and expensive to compute directly. The usual approach is an eigenvalue decomposition of the TCC, giving SOCS (Sum of Coherent Systems) kernels.

$$ I(x) = \sum_k \lambda_k |(\phi_k * M)(x)|^2 $$

Truncating to the kernels with the largest eigenvalues balances accuracy and speed; typically 10 to 30 kernels are kept.

![SOCS diagram](socs.svg)

## Limitations

The Hopkins model assumes a thin mask (Kirchhoff approximation). Under EUV and high-NA conditions mask 3D effects are significant and an M3D model correction is required.

Back to [Imaging models](README.md).
