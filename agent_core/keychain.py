import ctypes
import ctypes.util
from .chatlog_client import ChatlogError


SERVICE = "com.wechat-sales-agent.database-key"


class KeychainStore:
    def __init__(self, service: str = SERVICE):
        self.service = service

    def put(self, account_id: str, secret: str) -> None:
        security = ctypes.CDLL(ctypes.util.find_library("Security"))
        core_foundation = ctypes.CDLL(ctypes.util.find_library("CoreFoundation"))
        service = self.service.encode("utf-8")
        account = account_id.encode("utf-8")
        password = secret.encode("utf-8")
        item = ctypes.c_void_p()
        security.SecKeychainFindGenericPassword.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        security.SecKeychainFindGenericPassword.restype = ctypes.c_int32
        status = security.SecKeychainFindGenericPassword(
            None,
            len(service),
            service,
            len(account),
            account,
            None,
            None,
            ctypes.byref(item),
        )
        if status == 0:
            security.SecKeychainItemModifyAttributesAndData.argtypes = [
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_uint32,
                ctypes.c_void_p,
            ]
            security.SecKeychainItemModifyAttributesAndData.restype = ctypes.c_int32
            status = security.SecKeychainItemModifyAttributesAndData(
                item, None, len(password), password
            )
            core_foundation.CFRelease(item)
        elif status == -25300:
            security.SecKeychainAddGenericPassword.argtypes = [
                ctypes.c_void_p,
                ctypes.c_uint32,
                ctypes.c_void_p,
                ctypes.c_uint32,
                ctypes.c_void_p,
                ctypes.c_uint32,
                ctypes.c_void_p,
                ctypes.c_void_p,
            ]
            security.SecKeychainAddGenericPassword.restype = ctypes.c_int32
            status = security.SecKeychainAddGenericPassword(
                None,
                len(service),
                service,
                len(account),
                account,
                len(password),
                password,
                None,
            )
        if status != 0:
            raise ChatlogError(
                "KEYCHAIN_WRITE_FAILED",
                "Database key could not be stored in macOS Keychain.",
            )

    def get(self, account_id: str) -> str:
        security = ctypes.CDLL(ctypes.util.find_library("Security"))
        core_foundation = ctypes.CDLL(ctypes.util.find_library("CoreFoundation"))
        service = self.service.encode("utf-8")
        account = account_id.encode("utf-8")
        length = ctypes.c_uint32()
        data = ctypes.c_void_p()
        item = ctypes.c_void_p()
        security.SecKeychainFindGenericPassword.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_void_p),
        ]
        security.SecKeychainFindGenericPassword.restype = ctypes.c_int32
        status = security.SecKeychainFindGenericPassword(
            None,
            len(service),
            service,
            len(account),
            account,
            ctypes.byref(length),
            ctypes.byref(data),
            ctypes.byref(item),
        )
        if status != 0:
            raise ChatlogError(
                "KEYCHAIN_READ_FAILED",
                "Database key could not be read from macOS Keychain.",
            )
        try:
            return ctypes.string_at(data, length.value).decode("utf-8")
        finally:
            security.SecKeychainItemFreeContent(None, data)
            core_foundation.CFRelease(item)

    def put_and_verify(self, account_id: str, secret: str) -> None:
        self.put(account_id, secret)
        if self.get(account_id) != secret:
            raise ChatlogError(
                "KEYCHAIN_VERIFY_FAILED",
                "Database key did not round-trip through macOS Keychain.",
            )
