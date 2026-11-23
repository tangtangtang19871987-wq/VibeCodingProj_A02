# Resist models

A resist model converts the aerial image into the developed contour.

## Threshold model

The simplest resist model is the constant threshold resist model (CTR): regions where the aerial image intensity exceeds the threshold are treated as exposed.

## Diffusion and convolution models

More accurate compact models convolve the aerial image with a Gaussian before thresholding to approximate acid diffusion. The diffusion length is a key parameter that must be calibrated with metrology data.
