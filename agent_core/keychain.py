import subprocess

from .chatlog_client import ChatlogError


SERVICE = "com.wechat-sales-agent.database-key"


class KeychainStore:
    def put(self, account_id: str, secret: str) -> None:
        command = [
            "/usr/bin/security", "add-generic-password",
            "-a", account_id,
            "-s", SERVICE,
            "-U",
            "-w", secret,
        ]
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            raise ChatlogError("KEYCHAIN_WRITE_FAILED", "Database key could not be stored in macOS Keychain.")

    def get(self, account_id: str) -> str:
        command = [
            "/usr/bin/security", "find-generic-password",
            "-a", account_id,
            "-s", SERVICE,
            "-w",
        ]
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            raise ChatlogError("KEYCHAIN_READ_FAILED", "Database key could not be read from macOS Keychain.")
        return completed.stdout.rstrip("\n")

    def put_and_verify(self, account_id: str, secret: str) -> None:
        self.put(account_id, secret)
        if self.get(account_id) != secret:
            raise ChatlogError("KEYCHAIN_VERIFY_FAILED", "Database key did not round-trip through macOS Keychain.")
