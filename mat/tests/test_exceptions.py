"""
Tests for custom exception types in the mat package.

This test module verifies that LockTimeoutError and CommandTimeoutError
are properly defined, inherit from Exception, have correct docstrings,
and can be raised and caught correctly.
"""

import pytest

from mat import LockTimeoutError, CommandTimeoutError


class TestLockTimeoutError:
    """Test LockTimeoutError exception."""

    def test_lock_timeout_error_creation(self) -> None:
        """Test that LockTimeoutError can be instantiated."""
        error = LockTimeoutError("Could not acquire lock within timeout")
        assert isinstance(error, Exception)
        assert str(error) == "Could not acquire lock within timeout"

    def test_lock_timeout_error_can_be_raised_and_caught(self) -> None:
        """Test that LockTimeoutError can be raised and caught correctly."""
        with pytest.raises(LockTimeoutError):
            raise LockTimeoutError("Lock acquisition timed out")

    def test_lock_timeout_error_has_docstring(self) -> None:
        """Test that LockTimeoutError has a docstring explaining its use."""
        assert LockTimeoutError.__doc__ is not None
        assert "timeout" in LockTimeoutError.__doc__.lower()
        assert "lock" in LockTimeoutError.__doc__.lower()

    def test_lock_timeout_error_inherits_from_exception(self) -> None:
        """Test that LockTimeoutError properly inherits from Exception."""
        assert issubclass(LockTimeoutError, Exception)


class TestCommandTimeoutError:
    """Test CommandTimeoutError exception."""

    def test_command_timeout_error_creation(self) -> None:
        """Test that CommandTimeoutError can be instantiated."""
        error = CommandTimeoutError("Command execution exceeded timeout")
        assert isinstance(error, Exception)
        assert str(error) == "Command execution exceeded timeout"

    def test_command_timeout_error_can_be_raised_and_caught(self) -> None:
        """Test that CommandTimeoutError can be raised and caught correctly."""
        with pytest.raises(CommandTimeoutError):
            raise CommandTimeoutError("Command execution timed out")

    def test_command_timeout_error_has_docstring(self) -> None:
        """Test that CommandTimeoutError has a docstring explaining its use."""
        assert CommandTimeoutError.__doc__ is not None
        assert "timeout" in CommandTimeoutError.__doc__.lower()
        assert "command" in CommandTimeoutError.__doc__.lower()

    def test_command_timeout_error_inherits_from_exception(self) -> None:
        """Test that CommandTimeoutError properly inherits from Exception."""
        assert issubclass(CommandTimeoutError, Exception)


class TestExceptionBehavior:
    """Test exception behavior and integration."""

    def test_exceptions_can_be_imported_from_mat(self) -> None:
        """Test that both exceptions can be imported from mat package."""
        from mat import LockTimeoutError as LTE
        from mat import CommandTimeoutError as CTE

        assert LTE is LockTimeoutError
        assert CTE is CommandTimeoutError

    def test_exceptions_are_different(self) -> None:
        """Test that the two exception types are distinct."""
        assert LockTimeoutError is not CommandTimeoutError
        assert not issubclass(LockTimeoutError, CommandTimeoutError)
        assert not issubclass(CommandTimeoutError, LockTimeoutError)

    def test_can_catch_lock_timeout_without_catching_command_timeout(self) -> None:
        """Test selective exception catching for LockTimeoutError."""
        with pytest.raises(LockTimeoutError):
            try:
                raise LockTimeoutError("timeout")
            except CommandTimeoutError:
                pytest.fail("Should not catch CommandTimeoutError")
            else:
                raise

    def test_can_catch_command_timeout_without_catching_lock_timeout(self) -> None:
        """Test selective exception catching for CommandTimeoutError."""
        with pytest.raises(CommandTimeoutError):
            try:
                raise CommandTimeoutError("timeout")
            except LockTimeoutError:
                pytest.fail("Should not catch LockTimeoutError")
            else:
                raise
