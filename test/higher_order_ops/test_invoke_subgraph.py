# Owner(s): ["module: functorch"]
# flake8: noqa: B950

import torch
import torch._dynamo
import torch._functorch
import torch._inductor
import torch._inductor.decomposition
from functorch.compile import aot_function, nop
from functorch.experimental.control_flow import UnsupportedAliasMutationException
from torch._higher_order_ops import create_invoke_subgraph_op
from torch.testing._internal.common_utils import run_tests, TestCase


def extract_graph(fx_g, _, graph_cell):
    graph_cell[0] = fx_g
    return fx_g


class TestInvokeSubgraph(TestCase):
    def test_simple(self):
        def gn(x, y):
            return (torch.mul(x, y),)

        def fn(x, y):
            return create_invoke_subgraph_op(gn, (x, y))[0]

        x = torch.randn(8, requires_grad=True)
        y = torch.randn(8, requires_grad=True)
        ref = gn(x, y)[0]

        x_clone = x.clone().detach().requires_grad_(True)
        y_clone = y.clone().detach().requires_grad_(True)
        res = fn(x_clone, y_clone)

        # Run backward
        ref.sum().backward()
        res.sum().backward()

        self.assertEqual(ref, res)
        self.assertEqual(x.grad, x_clone.grad)
        self.assertEqual(y.grad, y_clone.grad)

    def test_aot_function(self):
        def gn(x, y):
            return (torch.mul(x, y),)

        def fn(x, y):
            return create_invoke_subgraph_op(gn, (x, y))[0]

        x = torch.randn(8, requires_grad=True)
        y = torch.randn(8, requires_grad=True)
        ref = gn(x, y)[0]

        x_clone = x.clone().detach().requires_grad_(True)
        y_clone = y.clone().detach().requires_grad_(True)
        aot_fn = aot_function(fn, nop)
        res = aot_fn(x_clone, y_clone)

        # Run backward
        ref.sum().backward()
        res.sum().backward()

        self.assertEqual(ref, res)
        self.assertEqual(x.grad, x_clone.grad)
        self.assertEqual(y.grad, y_clone.grad)

    def test_multiple(self):
        n_layers = 2

        def cos(x):
            return (torch.cos(x),)

        def sin(x):
            return (torch.sin(x),)

        def fn(x):
            a = create_invoke_subgraph_op(cos, (x,))[0]
            b = create_invoke_subgraph_op(sin, (a,))[0]
            return create_invoke_subgraph_op(cos, (b,))[0]

        x = torch.randn(8, requires_grad=True)
        ref = fn(x)
        aot_fn = aot_function(fn, nop)
        res = aot_fn(x)

        self.assertEqual(ref, res)

    def test_input_mutation(self):
        def gn(x, y):
            x.add_(1)
            return (torch.mul(x, y),)

        def fn(x, y):
            return create_invoke_subgraph_op(gn, (x, y))[0]

        x = torch.randn(8, requires_grad=False)
        y = torch.randn(8, requires_grad=False)

        with self.assertRaisesRegex(
            UnsupportedAliasMutationException, "One of invoke_subgraph hop"
        ):
            aot_fn = aot_function(fn, nop)
            res = aot_fn(x, y)

    def test_input_aliasing(self):
        def gn(x, y):
            return (x, torch.mul(x, y))

        def fn(x, y):
            outs = create_invoke_subgraph_op(gn, (x, y))
            return outs[0] * outs[1]

        x = torch.randn(8, requires_grad=False)
        y = torch.randn(8, requires_grad=False)

        with self.assertRaisesRegex(
            UnsupportedAliasMutationException, "One of invoke_subgraph hop"
        ):
            aot_fn = aot_function(fn, nop)
            res = aot_fn(x, y)

    def test_differing_strides_for_grad_outs(self):
        class CustomOp(torch.autograd.Function):
            @staticmethod
            def forward(ctx, x):
                return torch.sin(x)

            @staticmethod
            def backward(ctx, grad_out):
                a = grad_out.view(12, 5)
                return torch.cos(torch.reshape(a, (3, 4, 5)))

        def gn(x):
            return (CustomOp.apply(x),)

        def fn(x):
            a = create_invoke_subgraph_op(gn, (x,))[0]
            # Force stride changes so that backward view causes a failure if
            # contiguous not called.
            b = torch.permute(a, (0, 2, 1))
            return b

        x = torch.randn(3, 4, 5, requires_grad=True)
        ref = torch.permute(gn(x)[0], (0, 2, 1))

        x_clone = x.clone().detach().requires_grad_(True)
        aot_fn = aot_function(fn, nop)
        res = aot_fn(x_clone)

        # Run backward
        ref.sum().backward()
        res.sum().backward()

        self.assertEqual(ref, res)
        self.assertEqual(x.grad, x_clone.grad)


if __name__ == "__main__":
    run_tests()
