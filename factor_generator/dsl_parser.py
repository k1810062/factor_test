"""DSL 解析器：公式字符串 → AST。"""

from dataclasses import dataclass
from typing import Any
from .dsl_grammar import is_operator, is_field, OPERATORS


# ── AST 节点类型 ──────────────────────────────────

@dataclass
class Num:
    val: float | int

@dataclass
class Field:
    name: str          # 原始名如 CLOSE

@dataclass
class BinOp:
    op: str            # + - * / > < >= <= == !=
    left: Any
    right: Any

@dataclass
class CmpOp:
    op: str
    left: Any
    right: Any

@dataclass
class UnaryOp:
    op: str            # -
    expr: Any

@dataclass
class Call:
    name: str          # 算子名
    args: list[Any]

@dataclass
class DSLScript:
    """完整的 DSL 脚本。"""
    expr: Any
    dsl: str = ''
    operators: set[str] = None
    fields: set[str] = None

    def __post_init__(self):
        self.operators = set()
        self.fields = set()
        _collect(self.expr, self.operators, self.fields)


def _collect(node, ops, fields):
    if isinstance(node, Call):
        ops.add(node.name)
        for a in node.args:
            _collect(a, ops, fields)
    elif isinstance(node, Field):
        fields.add(node.name)
    elif isinstance(node, (BinOp, CmpOp)):
        _collect(node.left, ops, fields)
        _collect(node.right, ops, fields)
    elif isinstance(node, UnaryOp):
        _collect(node.expr, ops, fields)


# ── Tokenizer ─────────────────────────────────────

class Tokenizer:
    def __init__(self, text: str):
        self.text = text
        self.pos = 0

    def peek(self) -> str | None:
        while self.pos < len(self.text) and self.text[self.pos] in ' \n\r\t':
            self.pos += 1
        if self.pos >= len(self.text):
            return None
        return self.text[self.pos]

    def next(self) -> str:
        c = self.peek()
        if c is None:
            raise EOFError('unexpected end')
        self.pos += 1
        return c

    def expect(self, expected: str):
        got = self.next()
        if got != expected:
            raise SyntaxError(f'expected {expected!r}, got {got!r}')

    def read_number(self) -> str:
        start = self.pos - 1
        while self.pos < len(self.text) and (self.text[self.pos].isdigit() or self.text[self.pos] == '.'):
            self.pos += 1
        return self.text[start:self.pos]

    def read_name(self) -> str:
        start = self.pos - 1
        while self.pos < len(self.text) and (self.text[self.pos].isalnum() or self.text[self.pos] == '_'):
            self.pos += 1
        return self.text[start:self.pos]

    def parse(self) -> Any:
        return self._expr()

    def _expr(self):
        left = self._comp()
        while self.peek() in ('+', '-'):
            op = self.next()
            right = self._comp()
            left = BinOp(op, left, right)
        return left

    def _comp(self):
        left = self._term()
        while self.peek() in ('>', '<', '=', '!'):
            two = self.text[self.pos:self.pos+2]
            if two in ('>=', '<=', '==', '!='):
                self.pos += 2
                right = self._term()
                left = CmpOp(two, left, right)
            else:
                op = self.next()
                right = self._term()
                left = CmpOp(op, left, right)
        return left

    def _term(self):
        left = self._factor()
        while self.peek() in ('*', '/'):
            op = self.next()
            right = self._factor()
            left = BinOp(op, left, right)
        return left

    def _factor(self):
        if self.peek() == '-':
            self.pos += 1
            return UnaryOp('-', self._factor())
        return self._call_or_atom()

    def _call_or_atom(self):
        c = self.peek()
        if c is None:
            raise SyntaxError('unexpected end')
        if c.isdigit():
            self.pos += 1
            return Num(float(self.read_number()))
        if c == '(':
            self.pos += 1
            expr = self._expr()
            self.expect(')')
            return expr
        if c.isalpha() or c == '_':
            self.pos += 1
            name = self.read_name()
            if self.peek() == '(':
                return self._finish_call(name)
            if is_operator(name):
                raise SyntaxError(f'operator {name} used without arguments')
            return Field(name)  # 未知标识符也作为字段处理，校验交给 codegen
        raise SyntaxError(f'unexpected character: {c!r}')

    def _finish_call(self, name: str):
        self.expect('(')
        args = []
        while self.peek() != ')':
            if args:
                self.expect(',')
            args.append(self._expr())
        self.expect(')')
        if name not in OPERATORS:
            raise SyntaxError(f'unknown operator: {name}')
        op = OPERATORS[name]
        if len(args) != len(op.params):
            raise SyntaxError(f'{name} expects {len(op.params)} args, got {len(args)}')
        return Call(name, args)


def parse_dsl(text: str) -> DSLScript:
    """解析 DSL 公式字符串，返回 DSLScript。"""
    raw = text.strip().upper()
    t = Tokenizer(raw)
    expr = t.parse()
    if t.peek() is not None:
        raise SyntaxError(f'unexpected trailing content')
    return DSLScript(expr, dsl=raw)
