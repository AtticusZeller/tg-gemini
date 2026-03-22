"""Tests for tg_gemini.models module."""

from tg_gemini.models import (
    Event,
    EventType,
    FileAttachment,
    ImageAttachment,
    Message,
    ModelOption,
    PreviewHandle,
    ReplyContext,
)


class TestEventType:
    """Tests for EventType enum."""

    def test_enum_values(self) -> None:
        """Test that all enum values are correct."""
        assert EventType.TEXT == "text"
        assert EventType.TOOL_USE == "tool_use"
        assert EventType.TOOL_RESULT == "tool_result"
        assert EventType.RESULT == "result"
        assert EventType.ERROR == "error"
        assert EventType.THINKING == "thinking"

    def test_enum_from_string(self) -> None:
        """Test creating enum from string."""
        assert EventType("text") == EventType.TEXT
        assert EventType("tool_use") == EventType.TOOL_USE
        assert EventType("error") == EventType.ERROR


class TestImageAttachment:
    """Tests for ImageAttachment dataclass."""

    def test_required_fields(self) -> None:
        """Test creation with required fields."""
        data = b"fake_image_data"
        img = ImageAttachment(mime_type="image/png", data=data)
        assert img.mime_type == "image/png"
        assert img.data == data
        assert img.file_name == ""  # default

    def test_all_fields(self) -> None:
        """Test creation with all fields."""
        data = b"fake_image_data"
        img = ImageAttachment(mime_type="image/jpeg", data=data, file_name="test.jpg")
        assert img.mime_type == "image/jpeg"
        assert img.data == data
        assert img.file_name == "test.jpg"


class TestFileAttachment:
    """Tests for FileAttachment dataclass."""

    def test_required_fields(self) -> None:
        """Test creation with required fields."""
        data = b"fake_file_data"
        file = FileAttachment(mime_type="application/pdf", data=data)
        assert file.mime_type == "application/pdf"
        assert file.data == data
        assert file.file_name == ""  # default

    def test_all_fields(self) -> None:
        """Test creation with all fields."""
        data = b"fake_file_data"
        file = FileAttachment(
            mime_type="text/plain", data=data, file_name="document.txt"
        )
        assert file.mime_type == "text/plain"
        assert file.data == data
        assert file.file_name == "document.txt"


class TestEvent:
    """Tests for Event dataclass."""

    def test_required_fields(self) -> None:
        """Test creation with required fields only."""
        event = Event(type=EventType.TEXT)
        assert event.type == EventType.TEXT
        assert event.content == ""  # default
        assert event.tool_name == ""  # default
        assert event.tool_input == ""  # default
        assert event.session_id == ""  # default
        assert event.done is False  # default
        assert event.error is None  # default

    def test_all_fields(self) -> None:
        """Test creation with all fields."""
        error = ValueError("test error")
        event = Event(
            type=EventType.TOOL_USE,
            content="Using tool",
            tool_name="search",
            tool_input='{"query": "test"}',
            session_id="sess_123",
            done=True,
            error=error,
        )
        assert event.type == EventType.TOOL_USE
        assert event.content == "Using tool"
        assert event.tool_name == "search"
        assert event.tool_input == '{"query": "test"}'
        assert event.session_id == "sess_123"
        assert event.done is True
        assert event.error is error

    def test_event_with_error_type(self) -> None:
        """Test creating an error event."""
        error = RuntimeError("something went wrong")
        event = Event(type=EventType.ERROR, error=error, content="Error occurred")
        assert event.type == EventType.ERROR
        assert event.error is error
        assert event.content == "Error occurred"


class TestMessage:
    """Tests for Message dataclass."""

    def test_required_fields(self) -> None:
        """Test creation with required fields only."""
        msg = Message(
            session_key="telegram:123456:789",
            platform="telegram",
            user_id="789",
            user_name="testuser",
            content="Hello world",
        )
        assert msg.session_key == "telegram:123456:789"
        assert msg.platform == "telegram"
        assert msg.user_id == "789"
        assert msg.user_name == "testuser"
        assert msg.content == "Hello world"
        assert msg.message_id == ""  # default
        assert msg.chat_name == ""  # default
        assert msg.images == []  # default
        assert msg.files == []  # default
        assert msg.reply_ctx is None  # default

    def test_all_fields(self) -> None:
        """Test creation with all fields."""
        img = ImageAttachment(mime_type="image/png", data=b"img")
        file = FileAttachment(mime_type="text/plain", data=b"file")
        reply_ctx = ReplyContext(chat_id=123456, message_id=42)
        msg = Message(
            session_key="telegram:123456:789",
            platform="telegram",
            user_id="789",
            user_name="testuser",
            content="Hello with attachments",
            message_id="100",
            chat_name="Test Chat",
            images=[img],
            files=[file],
            reply_ctx=reply_ctx,
        )
        assert msg.session_key == "telegram:123456:789"
        assert msg.platform == "telegram"
        assert msg.user_id == "789"
        assert msg.user_name == "testuser"
        assert msg.content == "Hello with attachments"
        assert msg.message_id == "100"
        assert msg.chat_name == "Test Chat"
        assert msg.images == [img]
        assert msg.files == [file]
        assert msg.reply_ctx is reply_ctx

    def test_empty_attachments_lists(self) -> None:
        """Test that default empty lists are independent."""
        msg1 = Message(
            session_key="telegram:1:1",
            platform="telegram",
            user_id="1",
            user_name="user1",
            content="test",
        )
        msg2 = Message(
            session_key="telegram:2:2",
            platform="telegram",
            user_id="2",
            user_name="user2",
            content="test",
        )
        # Ensure they have independent lists
        msg1.images.append(ImageAttachment(mime_type="image/png", data=b"x"))
        assert msg1.images != msg2.images
        assert len(msg2.images) == 0


class TestReplyContext:
    """Tests for ReplyContext dataclass."""

    def test_required_fields(self) -> None:
        """Test creation with required fields."""
        ctx = ReplyContext(chat_id=123456)
        assert ctx.chat_id == 123456
        assert ctx.message_id == 0  # default

    def test_all_fields(self) -> None:
        """Test creation with all fields."""
        ctx = ReplyContext(chat_id=123456, message_id=42)
        assert ctx.chat_id == 123456
        assert ctx.message_id == 42


class TestPreviewHandle:
    """Tests for PreviewHandle dataclass."""

    def test_all_fields(self) -> None:
        """Test creation with all fields (both required)."""
        handle = PreviewHandle(chat_id=123456, message_id=100)
        assert handle.chat_id == 123456
        assert handle.message_id == 100


class TestModelOption:
    """Tests for ModelOption dataclass."""

    def test_required_fields(self) -> None:
        """Test creation with required fields only."""
        opt = ModelOption(name="gemini-pro")
        assert opt.name == "gemini-pro"
        assert opt.desc == ""  # default
        assert opt.alias == ""  # default

    def test_all_fields(self) -> None:
        """Test creation with all fields."""
        opt = ModelOption(name="gemini-pro", desc="Google Gemini Pro", alias="pro")
        assert opt.name == "gemini-pro"
        assert opt.desc == "Google Gemini Pro"
        assert opt.alias == "pro"
