# Copyright 2024 Reo Yoneyama (Nagoya University)
#  MIT License (https://opensource.org/licenses/MIT)

"""Residual block modules."""

from logging import getLogger
from typing import Tuple

import torch
import torch.nn as nn
from torch import Tensor

from wavehax.modules import (
    BatchNorm2d,
    ComplexActivation,
    ComplexBatchNorm2d,
    ComplexConv2d,
    ComplexLayerNorm2d,
    DropPath,
    LayerNorm2d,
)

# A logger for this file
logger = getLogger(__name__)


class ConvNeXtBlock2d(nn.Module):
    """
    A 2D residual block module based on ConvNeXt architecture.

    Reference:
        - https://github.com/facebookresearch/ConvNeXt
    """

    def __init__(
        self,
        channels: int,
        mult_channels: int,
        kernel_size: int,
        drop_prob: float = 0.0,
        use_layer_norm: bool = True,
        layer_scale_init_value: float = None,
    ) -> None:
        """
        Initialize the ConvNeXtBlock2d module.

        Args:
            channels (int): Number of input and output channels for the block.
            mult_channels (int): Channel expansion factor used in pointwise convolutions.
            kernel_size (int): Size of the depthwise convolution kernel.
            drop_prob (float, optional): Probability of dropping paths for stochastic depth (default: 0.0).
            use_layer_norm (bool, optional): If True, layer normalization is used; otherwise,
                batch normalization is applied (default: True).
            layer_scale_init_value (float, optional): Initial value for the learnable layer scale parameter.
                If None, no scaling is applied (default: None).
        """
        super().__init__()
        if isinstance(kernel_size, int):
            kernel_size = (kernel_size, kernel_size)
        assert kernel_size[0] % 2 == 1, "Kernel size must be odd number."
        assert kernel_size[1] % 2 == 1, "Kernel size must be odd number."
        self.dwconv = nn.Conv2d(
            channels,
            channels,
            kernel_size,
            padding=(kernel_size[0] // 2, kernel_size[1] // 2),
            groups=channels,
            bias=False,
            padding_mode="reflect",
        )
        if use_layer_norm:
            self.norm = LayerNorm2d(channels)
        else:
            self.norm = BatchNorm2d(channels)
        self.pwconv1 = nn.Conv2d(channels, channels * mult_channels, 1)
        self.nonlinear = nn.GELU()
        self.pwconv2 = nn.Conv2d(channels * mult_channels, channels, 1)
        self.gamma = (
            nn.Parameter(
                layer_scale_init_value * torch.ones(1, channels, 1, 1),
                requires_grad=True,
            )
            if layer_scale_init_value is not None
            else None
        )
        self.drop_path = DropPath(drop_prob)

    def forward(self, x: Tensor) -> Tensor:
        """
        Calculate forward propagation.

        Args:
            x (Tensor): Input tensor with shape (batch, channels, height, width).

        Returns:
            Tensor: Output tensor of the same shape (batch, channels, height, width).
        """
        residual = x
        x = self.dwconv(x)
        x = self.norm(x)
        x = self.pwconv1(x)
        x = self.nonlinear(x)
        x = self.pwconv2(x)
        if self.gamma is not None:
            x = self.gamma * x
        x = residual + self.drop_path(x)
        return x


class ComplexConvNeXtBlock2d(nn.Module):
    """Complex-valued 2D residual block based on ConvNeXt architecture."""

    def __init__(
        self,
        channels: int,
        mult_channels: int,
        kernel_size: int,
        drop_prob: float = 0.0,
        use_layer_norm: bool = True,
        layer_scale_init_value: float = None,
    ) -> None:
        """
        Initialize the ComplexConvNeXtBlock2d module.

        Args:
            channels (int): Number of input and output channels for the block.
            mult_channels (int): Channel expansion factor used in pointwise convolutions.
            kernel_size (int): Size of the depthwise convolution kernel.
            drop_prob (float, optional): Probability of dropping paths for stochastic depth (default: 0.0).
            use_layer_norm (bool, optional): If True, layer normalization is used; otherwise,
                batch normalization is applied (default: True).
            layer_scale_init_value (float, optional): Initial value for the learnable layer scale parameter.
                If None, no scaling is applied (default: None).
        """
        super().__init__()
        if isinstance(kernel_size, int):
            kernel_size = (kernel_size, kernel_size)
        assert kernel_size[0] % 2 == 1, "Kernel size must be odd number."
        assert kernel_size[1] % 2 == 1, "Kernel size must be odd number."

        self.dwconv = ComplexConv2d(
            channels,
            channels,
            kernel_size,
            padding=(kernel_size[0] // 2, kernel_size[1] // 2),
            groups=channels,
            bias=False,
            padding_mode="reflect",
        )
        if use_layer_norm:
            self.norm = ComplexLayerNorm2d(channels)
        else:
            self.norm = ComplexBatchNorm2d(channels)
        self.pwconv1 = ComplexConv2d(channels, channels * mult_channels, 1)
        self.nonlinear = ComplexActivation(nn.GELU())
        self.pwconv2 = ComplexConv2d(channels * mult_channels, channels, 1)
        self.gamma = (
            nn.Parameter(
                layer_scale_init_value * torch.ones(1, channels, 1, 1),
                requires_grad=True,
            )
            if layer_scale_init_value is not None
            else None
        )
        self.drop_path = DropPath(drop_prob)

    def forward(self, real: Tensor, imag: Tensor) -> Tuple[Tensor, Tensor]:
        """
        Calculate forward propagation.

        Args:
            real (Tensor): Input real part tensor with shape (batch, channels, height, width).
            imag (Tensor): Input imaginary part tensor with shape (batch, channels, height, width).

        Returns:
            Tuple[Tensor, Tensor]: Complex tensor with shape (batch, channels, height, width).
        """
        residual_real, residual_imag = real, imag
        real, imag = self.dwconv(real, imag)
        real, imag = self.norm(real, imag)
        real, imag = self.pwconv1(real, imag)
        real, imag = self.nonlinear(real, imag)
        real, imag = self.pwconv2(real, imag)
        z = torch.stack([real, imag], dim=0)
        if self.gamma is not None:
            z = self.gamma * z
        z = self.drop_path(z)
        real = z[0] + residual_real
        imag = z[1] + residual_imag
        return real, imag
