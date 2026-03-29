"""Tests for the card system (card.py)."""

import pytest

from tg_gemini.card import (
    ButtonStyle,
    Card,
    CardActions,
    CardBuilder,
    CardButton,
    CardDivider,
    CardHeader,
    CardListItem,
    CardMarkdown,
    CardNote,
)

_DIVIDER = "──────────"


# ── Dataclass creation ─────────────────────────────────────────────────────


class TestDataclassCreation:
    def test_card_button_defaults(self) -> None:
        btn = CardButton(text="OK", callback_data="ok")
        assert btn.text == "OK"
        assert btn.callback_data == "ok"
        assert btn.style == ButtonStyle.DEFAULT

    def test_card_button_custom_style(self) -> None:
        btn = CardButton(text="Del", callback_data="del", style=ButtonStyle.DANGER)
        assert btn.style == ButtonStyle.DANGER

    def test_card_markdown_empty(self) -> None:
        assert CardMarkdown().text == ""

    def test_card_divider(self) -> None:
        CardDivider()  # should not raise

    def test_card_actions_empty(self) -> None:
        assert CardActions().buttons == []

    def test_card_note_empty(self) -> None:
        assert CardNote().text == ""

    def test_card_list_item_defaults(self) -> None:
        item = CardListItem()
        assert item.text == ""
        assert item.button is None

    def test_card_header_defaults(self) -> None:
        h = CardHeader()
        assert h.title == ""
        assert h.color == ""

    def test_card_defaults(self) -> None:
        c = Card()
        assert c.header is None
        assert c.elements == []


# ── CardBuilder fluent API ─────────────────────────────────────────────────


class TestCardBuilder:
    def test_empty_build(self) -> None:
        card = CardBuilder().build()
        assert card.header is None
        assert card.elements == []

    def test_title(self) -> None:
        card = CardBuilder().title("Hello").build()
        assert card.header is not None
        assert card.header.title == "Hello"
        assert card.header.color == ""

    def test_title_with_color(self) -> None:
        card = CardBuilder().title("Hi", color="blue").build()
        assert card.header is not None
        assert card.header.color == "blue"

    def test_markdown(self) -> None:
        card = CardBuilder().markdown("some text").build()
        assert len(card.elements) == 1
        assert isinstance(card.elements[0], CardMarkdown)
        assert card.elements[0].text == "some text"  # type: ignore[union-attr]

    def test_divider(self) -> None:
        card = CardBuilder().divider().build()
        assert isinstance(card.elements[0], CardDivider)

    def test_note(self) -> None:
        card = CardBuilder().note("Tip").build()
        assert isinstance(card.elements[0], CardNote)
        assert card.elements[0].text == "Tip"  # type: ignore[union-attr]

    def test_actions(self) -> None:
        btn1 = CardButton("Yes", "yes")
        btn2 = CardButton("No", "no")
        card = CardBuilder().actions(btn1, btn2).build()
        assert isinstance(card.elements[0], CardActions)
        assert card.elements[0].buttons == [btn1, btn2]  # type: ignore[union-attr]

    def test_list_item_without_button(self) -> None:
        card = CardBuilder().list_item("Item A").build()
        elem = card.elements[0]
        assert isinstance(elem, CardListItem)
        assert elem.text == "Item A"
        assert elem.button is None

    def test_list_item_with_button(self) -> None:
        btn = CardButton("Switch", "act:cmd:/switch 1")
        card = CardBuilder().list_item("Item A", btn).build()
        elem = card.elements[0]
        assert isinstance(elem, CardListItem)
        assert elem.button is btn

    def test_fluent_chaining(self) -> None:
        btn = CardButton("OK", "ok")
        card = (
            CardBuilder()
            .title("T")
            .markdown("text")
            .divider()
            .list_item("A")
            .list_item("B", btn)
            .actions(btn)
            .note("note")
            .build()
        )
        assert card.header is not None
        assert len(card.elements) == 6

    def test_builder_independent(self) -> None:
        """Two builders don't share state."""
        b1 = CardBuilder().title("A")
        b2 = CardBuilder().title("B")
        c1 = b1.build()
        c2 = b2.build()
        assert c1.header is not None
        assert c2.header is not None
        assert c1.header.title == "A"
        assert c2.header.title == "B"


# ── render_text ────────────────────────────────────────────────────────────


class TestRenderText:
    def test_empty_card(self) -> None:
        assert Card().render_text() == ""

    def test_header_only(self) -> None:
        card = CardBuilder().title("Header").build()
        assert card.render_text() == "<b>Header</b>"

    def test_markdown_element(self) -> None:
        card = CardBuilder().markdown("**bold**").build()
        assert "<b>bold</b>" in card.render_text()

    def test_empty_markdown_skipped(self) -> None:
        card = CardBuilder().markdown("").build()
        assert card.render_text() == ""

    def test_divider(self) -> None:
        card = CardBuilder().divider().build()
        assert card.render_text() == _DIVIDER

    def test_note(self) -> None:
        card = CardBuilder().note("tip").build()
        assert card.render_text() == "<i>tip</i>"

    def test_empty_note_skipped(self) -> None:
        card = CardBuilder().note("").build()
        assert card.render_text() == ""

    def test_list_item(self) -> None:
        card = CardBuilder().list_item("Item X").build()
        assert card.render_text() == "• Item X"

    def test_list_item_empty_text(self) -> None:
        card = CardBuilder().list_item("").build()
        assert card.render_text() == "• "

    def test_actions_not_rendered(self) -> None:
        btn = CardButton("Click", "data")
        card = CardBuilder().actions(btn).build()
        assert card.render_text() == ""

    def test_full_card_order(self) -> None:
        card = (
            CardBuilder()
            .title("Title")
            .markdown("text")
            .divider()
            .note("footer")
            .build()
        )
        rendered = card.render_text()
        parts = rendered.split("\n")
        assert parts[0] == "<b>Title</b>"
        assert _DIVIDER in parts
        assert "<i>footer</i>" in parts

    def test_header_color_ignored(self) -> None:
        card = CardBuilder().title("T", color="red").build()
        assert card.render_text() == "<b>T</b>"

    def test_header_empty_title_skipped(self) -> None:
        card = Card(header=CardHeader(title="", color="blue"))
        assert card.render_text() == ""


# ── collect_buttons ────────────────────────────────────────────────────────


class TestCollectButtons:
    def test_empty_card(self) -> None:
        assert Card().collect_buttons() == []

    def test_no_buttons(self) -> None:
        card = CardBuilder().markdown("text").note("note").build()
        assert card.collect_buttons() == []

    def test_card_actions_single_row(self) -> None:
        btn1 = CardButton("A", "a")
        btn2 = CardButton("B", "b")
        card = CardBuilder().actions(btn1, btn2).build()
        rows = card.collect_buttons()
        assert rows == [[btn1, btn2]]

    def test_card_actions_multiple_rows(self) -> None:
        btn1 = CardButton("A", "a")
        btn2 = CardButton("B", "b")
        card = CardBuilder().actions(btn1).actions(btn2).build()
        rows = card.collect_buttons()
        assert rows == [[btn1], [btn2]]

    def test_list_item_with_button(self) -> None:
        btn = CardButton("Switch", "sw")
        card = CardBuilder().list_item("Item", btn).build()
        rows = card.collect_buttons()
        assert rows == [[btn]]

    def test_list_item_without_button_skipped(self) -> None:
        card = CardBuilder().list_item("Item").build()
        assert card.collect_buttons() == []

    def test_mixed_elements(self) -> None:
        btn1 = CardButton("A", "a")
        btn2 = CardButton("B", "b")
        btn3 = CardButton("C", "c")
        card = (
            CardBuilder()
            .list_item("I1", btn1)
            .list_item("I2")
            .list_item("I3", btn2)
            .actions(btn3)
            .build()
        )
        rows = card.collect_buttons()
        assert rows == [[btn1], [btn2], [btn3]]

    def test_empty_actions_skipped(self) -> None:
        card = Card(elements=[CardActions(buttons=[])])
        assert card.collect_buttons() == []


# ── has_buttons ────────────────────────────────────────────────────────────


class TestHasButtons:
    def test_false_when_no_buttons(self) -> None:
        card = CardBuilder().markdown("text").build()
        assert card.has_buttons() is False

    def test_true_when_actions(self) -> None:
        card = CardBuilder().actions(CardButton("X", "x")).build()
        assert card.has_buttons() is True

    def test_true_when_list_item_button(self) -> None:
        card = CardBuilder().list_item("I", CardButton("Y", "y")).build()
        assert card.has_buttons() is True

    def test_false_empty_card(self) -> None:
        assert Card().has_buttons() is False


# ── ButtonStyle enum ───────────────────────────────────────────────────────


class TestButtonStyle:
    def test_values(self) -> None:
        assert ButtonStyle.PRIMARY == "primary"
        assert ButtonStyle.DEFAULT == "default"
        assert ButtonStyle.DANGER == "danger"

    @pytest.mark.parametrize(
        "style", [ButtonStyle.PRIMARY, ButtonStyle.DEFAULT, ButtonStyle.DANGER]
    )
    def test_all_styles(self, style: ButtonStyle) -> None:
        btn = CardButton("X", "x", style=style)
        assert btn.style == style
