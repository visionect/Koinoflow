from apps.connectors.confluence.parser import parse_storage_to_markdown


class TestHeadings:
    def test_h1(self):
        result = parse_storage_to_markdown("<h1>Introduction</h1>")
        assert "# Introduction" in result

    def test_h2(self):
        result = parse_storage_to_markdown("<h2>Overview</h2>")
        assert "## Overview" in result

    def test_h6(self):
        result = parse_storage_to_markdown("<h6>Deep</h6>")
        assert "###### Deep" in result


class TestInlineFormatting:
    def test_bold(self):
        assert "**bold**" in parse_storage_to_markdown("<strong>bold</strong>")
        assert "**bold**" in parse_storage_to_markdown("<b>bold</b>")

    def test_italic(self):
        assert "_italic_" in parse_storage_to_markdown("<em>italic</em>")
        assert "_italic_" in parse_storage_to_markdown("<i>italic</i>")

    def test_inline_code(self):
        assert "`code`" in parse_storage_to_markdown("<code>code</code>")

    def test_link(self):
        result = parse_storage_to_markdown('<a href="https://example.com">Example</a>')
        assert "[Example](https://example.com)" in result


class TestLists:
    def test_unordered_list(self):
        html = "<ul><li>Apple</li><li>Banana</li></ul>"
        result = parse_storage_to_markdown(html)
        assert "- Apple" in result
        assert "- Banana" in result

    def test_ordered_list(self):
        html = "<ol><li>First</li><li>Second</li></ol>"
        result = parse_storage_to_markdown(html)
        assert "1. First" in result
        assert "2. Second" in result


class TestCodeBlock:
    def test_pre_block(self):
        result = parse_storage_to_markdown("<pre>some code here</pre>")
        assert "```" in result
        assert "some code here" in result


class TestTable:
    def test_basic_table(self):
        html = """
        <table>
          <tr><th>Name</th><th>Role</th></tr>
          <tr><td>Alice</td><td>Engineer</td></tr>
        </table>
        """
        result = parse_storage_to_markdown(html)
        assert "| Name" in result
        assert "| Alice" in result
        assert "---" in result

    def test_pipe_escaped_in_cell(self):
        html = "<table><tr><th>A|B</th></tr><tr><td>val</td></tr></table>"
        result = parse_storage_to_markdown(html)
        assert "A\\|B" in result


class TestAtlassianMacros:
    def test_macro_without_body_produces_no_output(self):
        xml = (
            '<ac:structured-macro ac:name="info">'
            '<ac:parameter ac:name="title">Note</ac:parameter>'
            "</ac:structured-macro>"
        )
        result = parse_storage_to_markdown(xml)
        assert result.strip() == ""

    def test_macro_with_body_preserved(self):
        xml = """
        <ac:structured-macro ac:name="info">
          <ac:rich-text-body><p>Important note here</p></ac:rich-text-body>
        </ac:structured-macro>
        """
        result = parse_storage_to_markdown(xml)
        assert "Important note here" in result

    def test_image_placeholder(self):
        xml = '<ac:image><ri:attachment ri:filename="diagram.png"/></ac:image>'
        result = parse_storage_to_markdown(xml)
        assert "diagram.png" in result

    def test_script_stripped(self):
        xml = "<p>Text</p><script>alert('xss')</script>"
        result = parse_storage_to_markdown(xml)
        assert "alert" not in result
        assert "Text" in result

    def test_style_stripped(self):
        xml = "<p>Content</p><style>.cls { color: red; }</style>"
        result = parse_storage_to_markdown(xml)
        assert ".cls" not in result
        assert "Content" in result

    def test_ac_parameter_stripped(self):
        xml = "<p>Text</p><ac:parameter ac:name='title'>Should not appear</ac:parameter>"
        result = parse_storage_to_markdown(xml)
        assert "Should not appear" not in result
