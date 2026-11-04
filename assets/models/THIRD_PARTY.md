# Third-party model

`u2netp.onnx` is U²-Net-p, the small variant of U²-Net (Qin, Zhang, Huang,
Dehghan, Zaiane, Jagersand, "U²-Net: Going Deeper with Nested U-Structure for
Salient Object Detection", Pattern Recognition 2020), released under the
Apache License 2.0 at https://github.com/xuebinqin/U-2-Net. The ONNX export
used here is the one distributed by the rembg project
(https://github.com/danielgatis/rembg, release v0.0.0, file `u2netp.onnx`,
SHA-256 309c8469258dda742793dce0ebea8e6dd393174f89934733ecc8b14c76f4ddd8).

FitCheck.AI uses it only to separate a garment from the background of a photo
(`assets/js/local/images.js`, run with onnxruntime-web). The other files in this folder are trained by
`notebooks/FitCheck_AI_ML_Analysis.ipynb`.
