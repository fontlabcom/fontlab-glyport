# this_file: src/fontlab_glyport/_py2.py
"""Selected fissix fixers and classic-division CST rewriting."""

from fissix import pygram, pytree
from fissix.fixer_util import Call, Comma, Name
from fissix.pgen2 import token
from fissix.refactor import RefactoringTool

FIXERS = (
    ("print_statement", "print"),
    ("except_comma", "except"),
    ("exec_statement", "exec"),
    ("backticks", "repr"),
    ("ne_diamond", "ne"),
    ("raise_tuple", "raise"),
    ("dict_iter", "dict"),
    ("xrange", "xrange"),
)


def parse(source: str) -> pytree.Node:
    """Parse Python 2 concrete syntax without importing or running the source."""
    return RefactoringTool([]).refactor_string(
        source if source.endswith("\n") else source + "\n", "<source>"
    )


def lexical(tree: pytree.Node, kind: str) -> str:
    """Separate literal and builtin changes into independently identified stages."""
    for leaf in tree.leaves():
        value = leaf.value
        if (
            kind == "long_literal"
            and leaf.type == token.NUMBER
            and value[-1:] in ("l", "L")
        ):
            leaf.value = value[:-1]
        elif (
            kind == "octal_literal"
            and leaf.type == token.NUMBER
            and value.isdigit()
            and value.startswith("0")
            and len(set(value)) > 1
        ):
            leaf.value = "0o" + value[1:]
        elif kind == "unicode_builtin" and leaf.type == token.NAME:
            leaf.value = {"unicode": "str", "unichr": "chr", "basestring": "str"}.get(
                value, value
            )
        elif kind == "unicode_literals" and leaf.type == token.STRING:
            # Reuse fissix's escape handling; operate only on string leaves.
            from fissix.fixes.fix_unicode import FixUnicode

            fixer = FixUnicode({}, [])
            fixer.start_tree(tree, "<source>")
            replacement = fixer.transform(leaf, {})
            if replacement is not None:
                leaf.value = replacement.value
    return str(tree)


def division(tree: pytree.Node) -> str:
    """Fold terms left-to-right; wrap only / with the runtime dispatch helper."""
    if "division" in tree.future_features:
        return str(tree)
    syms = pygram.python_symbols
    for leaf in tree.leaves():
        if leaf.value == "/=":
            raise SyntaxError(
                "Python 2 augmented division requires manual adaptation",
                ("<source>", leaf.lineno, leaf.column + 1, ""),
            )
    for node in list(tree.post_order()):
        if node.type != syms.term or not any(
            c.type == token.SLASH for c in node.children
        ):
            continue
        parts = [c.clone() for c in node.children]
        prefix = node.prefix
        left = parts[0]
        left.prefix = ""
        for operator, right in zip(parts[1::2], parts[2::2]):
            if operator.type == token.SLASH:
                right.prefix = ""
                left = Call(Name("_glyport_div"), [left, Comma(), right])
            else:
                left = pytree.Node(syms.term, [left, operator, right])
        left.prefix = prefix
        node.replace(left)
    return str(tree)
