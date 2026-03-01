<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: MIT -->

# ERA switch automation using NVIDIA NVUE Collection

This repository contains the files to set up ERA configuration on the core switches. You can change the values in the inventory files to customize the variables.

Please see each individual folder for configuration specific to that deployment type.

Individual releases for different versions are available for download as zip files through the GitHub GUI or by using cURL:
curl -LO https://github.com/NVIDIA/enterprise-ras/releases/tag/<release-tag>.zip

Release tags for the Spectrum ERA releases follow the pattern:
sp-<architecture>-v<version-number>
example: sp-2-8-9-400-v3.0.0

## Latest Release table

| Version | Architecture | Release tag |
|---------|--------------|-------------|
| 3.0.0   | 2-4-3-200    | `sp-2-4-3-200-v3.0.0` |
| 3.0.0   | 2-8-5-200    | `sp-2-8-5-200-v3.0.0` |
| 3.0.0   | 2-8-9-400    | `sp-2-8-9-400-v3.0.0` |

