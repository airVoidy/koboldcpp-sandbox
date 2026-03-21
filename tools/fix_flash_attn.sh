#!/bin/bash
# Fix flash-attn: install from conda-forge with matching torch
CONDA=/home/vairy/miniconda3/bin/conda
PIP=/home/vairy/miniconda3/bin/pip
PY=/home/vairy/miniconda3/bin/python

echo "=== Installing flash-attn + pytorch from conda-forge ==="
$CONDA install conda-forge::flash-attn conda-forge::pytorch -y 2>&1

echo "=== Testing ==="
$PY -c "
import torch
print('torch', torch.__version__)
from flash_attn import flash_attn_func
q = torch.randn(1, 8, 32, 64, dtype=torch.bfloat16, device='cuda')
k = torch.randn(1, 8, 32, 64, dtype=torch.bfloat16, device='cuda')
v = torch.randn(1, 8, 32, 64, dtype=torch.bfloat16, device='cuda')
out = flash_attn_func(q, k, v)
print('flash_attn GPU test OK, shape:', out.shape)
"
