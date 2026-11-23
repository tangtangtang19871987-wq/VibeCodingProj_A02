# OPC overview

Optical proximity correction (OPC) modifies the mask pattern to compensate for pattern distortion during imaging, so that the contour on the wafer is as close as possible to the design target.

## Model-based OPC

Model-based OPC fragments pattern edges into segments and iteratively moves the segments to minimize EPE. It depends on a calibrated [imaging model](../imaging/hopkins.md) and [resist model](../imaging/resist.md).

## Rule-based OPC

Rule-based OPC adds biases and serifs from lookup-table rules; it is fast but of limited accuracy and is mainly used at mature nodes.
