"""AD authentication with validated LDAPS and explicit transitive group mapping."""

import ssl
from typing import Any
from uuid import UUID

from ldap3 import NONE, SUBTREE, Connection, Server, Tls  # type: ignore[import-untyped]
from ldap3.core.exceptions import (  # type: ignore[import-untyped]
    LDAPException,
    LDAPInvalidCredentialsResult,
)
from ldap3.utils.conv import escape_filter_chars  # type: ignore[import-untyped]
from ldap3.utils.dn import parse_dn  # type: ignore[import-untyped]

from .configuration import AuthConfigurationError, DirectoryConfig
from .providers import ProviderUnavailable, Subject, credentials_valid


def directory_server(config: DirectoryConfig) -> Any:
    # Python3.13 PROTOCOL_TLS_CLIENT defaults to minimum TLS1.2. ldap3 disables
    # SSLContext hostname checks but performs its own exact certificate check.
    # Validate the operator-supplied CA at provider initialization, before login.
    ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH, cafile=config.ca_file)
    return Server(
        config.hostname,
        port=636,
        use_ssl=True,
        get_info=NONE,
        connect_timeout=config.timeout_seconds,
        tls=Tls(
            validate=ssl.CERT_REQUIRED,
            version=ssl.PROTOCOL_TLS_CLIENT,
            ca_certs_file=config.ca_file,
            sni=config.hostname,
        ),
    )


def _connect(server: Any, config: DirectoryConfig, user: str, password: str) -> Any:
    return Connection(
        server,
        user=user,
        password=password,
        auto_referrals=False,
        read_only=True,
        receive_timeout=config.timeout_seconds,
        raise_exceptions=True,
        check_names=False,
        auto_range=False,
    )


def _entries(
    connection: Any, config: DirectoryConfig, query: str, attributes: list[str], limit: int
) -> list[dict[str, Any]]:
    if not connection.search(
        config.base_dn,
        query,
        search_scope=SUBTREE,
        attributes=attributes,
        size_limit=limit,
        time_limit=config.timeout_seconds,
    ):
        raise ProviderUnavailable()
    if connection.result.get("result") != 0:
        raise ProviderUnavailable()
    response = connection.response
    if not isinstance(response, list) or len(response) > limit:
        raise ProviderUnavailable()
    if any(not isinstance(item, dict) or item.get("type") != "searchResEntry" for item in response):
        return []  # Referrals and unexpected response types cannot grant access.
    return response


class DirectoryProvider:
    def __init__(self, config: DirectoryConfig) -> None:
        self.config = config
        try:
            for dn in (config.base_dn, config.bind_dn, *config.group_roles):
                parse_dn(dn, escape=False, strip=True)
            self.server = directory_server(config)
        except (LDAPException, OSError, ValueError):
            raise AuthConfigurationError() from None

    def authenticate(self, username: str, password: str) -> Subject | None:
        if not credentials_valid(username, password):
            return None
        service = personal = None
        try:
            server = self.server
            service = _connect(server, self.config, self.config.bind_dn, self.config.bind_password)
            if not service.bind():
                raise ProviderUnavailable()
            query = (
                "(&(objectClass=user)(objectCategory=person)(sAMAccountName="
                + escape_filter_chars(username)
                + "))"
            )
            entries = _entries(service, self.config, query, ["sAMAccountName", "objectGUID"], 2)
            if len(entries) != 1:
                return None
            entry = entries[0]
            dn = entry.get("dn")
            if not isinstance(dn, str) or len(dn) > 2048:
                return None
            parse_dn(dn, escape=False, strip=True)
            account = entry.get("attributes", {}).get("sAMAccountName")
            if isinstance(account, list) and len(account) == 1:
                account = account[0]
            if not isinstance(account, str) or account.lower() != username.lower():
                return None
            guid = entry.get("raw_attributes", {}).get("objectGUID")
            if (
                not isinstance(guid, list)
                or len(guid) != 1
                or not isinstance(guid[0], bytes)
                or len(guid[0]) != 16
            ):
                return None
            subject = str(UUID(bytes_le=guid[0]))
            personal = _connect(server, self.config, dn, password)
            try:
                if not personal.bind():
                    return None
            except LDAPInvalidCredentialsResult:
                return None
            # LDAP_MATCHING_RULE_IN_CHAIN resolves direct and nested AD groups.
            allowed = "".join(
                "(distinguishedName=" + escape_filter_chars(group) + ")"
                for group in self.config.group_roles
            )
            groups = _entries(
                service,
                self.config,
                "(&(objectClass=group)(|"
                + allowed
                + ")(member:1.2.840.113556.1.4.1941:="
                + escape_filter_chars(dn)
                + "))",
                ["distinguishedName"],
                33,
            )
            assigned: set[str] = set()
            for group in groups:
                group_dn = group.get("dn")
                if (
                    not isinstance(group_dn, str)
                    or group_dn.casefold() not in self.config.group_roles
                ):
                    return None
                assigned.update(self.config.group_roles[group_dn.casefold()])
            return (
                Subject("ldap", subject, account.lower(), frozenset(assigned)) if assigned else None
            )
        except (LDAPException, OSError, ValueError):
            raise ProviderUnavailable() from None
        finally:
            for connection in (personal, service):
                if connection is not None:
                    try:
                        connection.unbind()
                    except (LDAPException, OSError):
                        pass
