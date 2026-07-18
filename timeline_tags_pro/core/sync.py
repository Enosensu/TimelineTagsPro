"""Text-line <-> content string synchronization.

Pure data-shaping helpers. No Blender context dependencies.
"""


def sync_lines_to_content(item):
    """Merge multi-line text_lines into a single content string.

    Faithful to user input: trailing empty lines are preserved.
    """
    lines = [line.body for line in item.text_lines]
    item["content"] = "\n".join(lines)


def sync_content_to_lines(item):
    """Split a content string back into text_lines.

    Faithful to saved data: empty lines are preserved.
    """
    raw = item.get("content", "")
    item.text_lines.clear()

    if raw:
        # split('\n') preserves empty lines faithfully.
        lines = raw.split("\n")
        for txt in lines:
            new_line = item.text_lines.add()
            new_line.body = txt
    else:
        # Default: one empty line for easy input.
        item.text_lines.add()
