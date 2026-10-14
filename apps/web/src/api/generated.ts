export interface paths {
    "/api/v1/activity": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Activity */
        get: operations["activity_api_v1_activity_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/audit/changes/{change_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Evidence */
        get: operations["evidence_api_v1_audit_changes__change_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/audit/objects/{object_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Object Identity */
        get: operations["object_identity_api_v1_audit_objects__object_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/audit/search": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Search */
        post: operations["search_api_v1_audit_search_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/audit/sources/{source_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Status */
        get: operations["status_api_v1_audit_sources__source_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/audit/sources/{source_id}/directory": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Directory Status */
        get: operations["directory_status_api_v1_audit_sources__source_id__directory_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/login": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Login */
        post: operations["login_api_v1_auth_login_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/logout": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Logout */
        post: operations["logout_api_v1_auth_logout_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/me": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Me */
        get: operations["me_api_v1_auth_me_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/collectors/{collector_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Enable */
        patch: operations["enable_api_v1_collectors__collector_id__patch"];
        trace?: never;
    };
    "/api/v1/collectors/{collector_id}/rotate-token": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Rotate */
        post: operations["rotate_api_v1_collectors__collector_id__rotate_token_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/health/domains": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Health Domains */
        get: operations["health_domains_api_v1_health_domains_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/overview": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Overview */
        get: operations["overview_api_v1_overview_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/shares": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Share List */
        get: operations["share_list_api_v1_shares_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sources": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Sources */
        get: operations["sources_api_v1_sources_get"];
        put?: never;
        /** Register */
        post: operations["register_api_v1_sources_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sources/{source_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Source Detail */
        get: operations["source_detail_api_v1_sources__source_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sources/{source_id}/collectors": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Collectors */
        get: operations["list_collectors_api_v1_sources__source_id__collectors_get"];
        put?: never;
        /** Enroll */
        post: operations["enroll_api_v1_sources__source_id__collectors_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sources/{source_id}/freshness": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Source Freshness */
        get: operations["source_freshness_api_v1_sources__source_id__freshness_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/volumes": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Volume List */
        get: operations["volume_list_api_v1_volumes_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /** AccountObservation */
        AccountObservation: {
            /** Latest Attempt State */
            latest_attempt_state?: ("COLLECTING" | "COMPLETE" | "ERROR") | null;
            /** Observed At */
            observed_at?: string | null;
            /**
             * Provenance
             * @default LDAP_KERBEROS_SIGNED_SEALED
             * @constant
             */
            provenance: "LDAP_KERBEROS_SIGNED_SEALED";
            /** Snapshot Id */
            snapshot_id?: string | null;
            /**
             * State
             * @enum {string}
             */
            state: "CURRENT" | "STALE" | "UNKNOWN" | "PARTIAL" | "ERROR";
            user?: components["schemas"]["DirectoryUser"] | null;
            /**
             * Valid For Ms
             * @default 0
             */
            valid_for_ms: number;
        };
        /** Activity */
        Activity: {
            /**
             * Continuity
             * @enum {string}
             */
            continuity: "CONTINUOUS_SINCE_BASELINE" | "GAP" | "UNKNOWN";
            /**
             * Evaluated At
             * Format: date-time
             */
            evaluated_at: string;
            /** Items */
            items: components["schemas"]["ActivityItem"][];
            /** Limit */
            limit: number;
            /** Offset */
            offset: number;
            /**
             * Quality
             * @enum {string}
             */
            quality: "COMPLETE" | "PARTIAL" | "STALE" | "ESTIMATED" | "UNAVAILABLE";
            /** Total */
            total: number;
            /**
             * Window End At
             * Format: date-time
             */
            window_end_at: string;
            /**
             * Window Start At
             * Format: date-time
             */
            window_start_at: string;
        };
        /** ActivityItem */
        ActivityItem: {
            /** Actor */
            actor?: null;
            /** Client */
            client?: null;
            /** Confidence */
            confidence?: null;
            /**
             * Event Type
             * @enum {string}
             */
            event_type: "CREATE" | "WRITE" | "RENAME" | "DELETE" | "METADATA_CHANGE" | "SECURITY_CHANGE";
            /** File Id */
            file_id: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** New Relative Path */
            new_relative_path: string | null;
            /** Object Id */
            object_id: string | null;
            /**
             * Occurred At
             * Format: date-time
             */
            occurred_at: string;
            /** Old Relative Path */
            old_relative_path: string | null;
            /** Parent File Id */
            parent_file_id: string | null;
            /**
             * Path Quality
             * @enum {string}
             */
            path_quality: "COMPLETE" | "UNAVAILABLE";
            /**
             * Provenance
             * @enum {string}
             */
            provenance: "NTFS_USN" | "UNKNOWN";
            /** Reason Mask */
            reason_mask: string | null;
            /** Source Event Id */
            source_event_id: string | null;
            /**
             * Source Id
             * Format: uuid
             */
            source_id: string;
            /** Volume Identity */
            volume_identity: string;
        };
        /** ApiError */
        ApiError: {
            /** Detail */
            detail: string;
        };
        /** AuditActor */
        AuditActor: {
            /** Account */
            account: string | null;
            account_observation?: components["schemas"]["AccountObservation"] | null;
            /** Boot Id */
            boot_id: string;
            /** Client Ip */
            client_ip: string | null;
            client_observation?: components["schemas"]["ClientObservation"] | null;
            /** Domain */
            domain: string | null;
            /**
             * Host Id
             * Format: uuid
             */
            host_id: string;
            /**
             * Identity Evidence Id
             * Format: uuid
             */
            identity_evidence_id: string;
            /** Logon Id */
            logon_id: string;
            /** Sid */
            sid: string;
            /** Workstation */
            workstation: string | null;
        };
        /** AuditCandidateView */
        AuditCandidateView: {
            /** Classification */
            classification: string;
            evidence: components["schemas"]["AuditRecordView"];
            /** Method */
            method: string;
            /** Reason */
            reason: string;
            /** Rule Version */
            rule_version: string;
        };
        /** AuditEvent */
        AuditEvent: {
            /** Access Mask */
            access_mask?: number | null;
            /** Account */
            account?: string | null;
            /** Boot Id */
            boot_id: string;
            /**
             * Channel
             * @default Security
             * @constant
             */
            channel: "Security";
            /** Client Ip */
            client_ip?: string | null;
            /** Domain */
            domain?: string | null;
            /**
             * Event Id
             * @enum {integer}
             */
            event_id: 4663 | 4660 | 4624 | 1102;
            /**
             * Generation
             * Format: uuid
             */
            generation: string;
            /** Handle Id */
            handle_id?: number | null;
            /**
             * Host Id
             * Format: uuid
             */
            host_id: string;
            /** Linked Record Ids */
            linked_record_ids?: number[];
            /** Logon Id */
            logon_id?: number | null;
            /** Logon Type */
            logon_type?: number | null;
            /** Object Type */
            object_type?: string | null;
            /**
             * Occurred At
             * Format: date-time
             */
            occurred_at: string;
            /** Path */
            path?: string | null;
            /**
             * Path Quality
             * @default UNKNOWN
             * @constant
             */
            path_quality: "UNKNOWN";
            /** Process Id */
            process_id?: number | null;
            /** Process Name */
            process_name?: string | null;
            /**
             * Provider
             * Format: uuid
             */
            provider: string;
            /**
             * Quality
             * @default PARTIAL
             * @enum {string}
             */
            quality: "COMPLETE" | "PARTIAL";
            /** Record Id */
            record_id: number;
            /** Sid */
            sid?: string | null;
            /** Version */
            version: number;
            /** Volume Id */
            volume_id?: string | null;
            /** Workstation */
            workstation?: string | null;
        };
        /** AuditHealth */
        AuditHealth: {
            /**
             * Backlog Bytes
             * @default 0
             */
            backlog_bytes: number;
            /**
             * Backlog Count
             * @default 0
             */
            backlog_count: number;
            /** Bookmark Age Seconds */
            bookmark_age_seconds?: number | null;
            /** Boot Id */
            boot_id?: string | null;
            /** Configured */
            configured: boolean;
            /** Error Code */
            error_code?: string | null;
            /**
             * Filtered Count
             * @default 0
             */
            filtered_count: number;
            /** Gap */
            gap?: string | null;
            /** Generation */
            generation?: string | null;
            /**
             * Host Id
             * Format: uuid
             */
            host_id: string;
            /** Last Accepted At */
            last_accepted_at?: string | null;
            /** Last Collected At */
            last_collected_at?: string | null;
            /**
             * Policy Verified
             * @default false
             */
            policy_verified: boolean;
            /**
             * Quarantine
             * @default false
             */
            quarantine: boolean;
            /**
             * Read Count
             * @default 0
             */
            read_count: number;
            /** Readiness Age Seconds */
            readiness_age_seconds?: number | null;
            /** Readiness Checked At */
            readiness_checked_at?: string | null;
            /** Readiness Complete */
            readiness_complete?: boolean | null;
            /** Readiness Duration Seconds */
            readiness_duration_seconds?: number | null;
            /** Readiness Error */
            readiness_error?: string | null;
            /** Readiness Objects */
            readiness_objects?: number | null;
            /** Readiness Stale */
            readiness_stale?: boolean | null;
            /** Remaining Record Margin */
            remaining_record_margin?: number | null;
            /**
             * Sacl Verified
             * @default false
             */
            sacl_verified: boolean;
            /**
             * State
             * @enum {string}
             */
            state: "NOT_CONFIGURED" | "OBSERVE" | "HEALTHY" | "GAP" | "BACKPRESSURE" | "ERROR";
        };
        /** AuditObject */
        AuditObject: {
            /** File Id */
            file_id: string;
            /**
             * Object Id
             * Format: uuid
             */
            object_id: string;
            /**
             * Source Id
             * Format: uuid
             */
            source_id: string;
            /** Volume Identity */
            volume_identity: string;
        };
        /** AuditPage */
        AuditPage: {
            /**
             * Evaluated At
             * Format: date-time
             */
            evaluated_at: string;
            /** Has More */
            has_more: boolean;
            /** Items */
            items: components["schemas"]["AuditRecordView"][];
            /** Limit */
            limit: number;
            /** Offset */
            offset: number;
        };
        /** AuditRecordView */
        AuditRecordView: {
            account_observation?: components["schemas"]["AccountObservation"] | null;
            /**
             * Audit Collector Id
             * Format: uuid
             */
            audit_collector_id: string;
            client_observation?: components["schemas"]["ClientObservation"] | null;
            /** Digest */
            digest: string;
            evidence: components["schemas"]["AuditEvent"];
            /**
             * First Received At
             * Format: date-time
             */
            first_received_at: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Numeric Fields */
            numeric_fields: {
                [key: string]: string;
            };
            /**
             * Source Id
             * Format: uuid
             */
            source_id: string;
        };
        /** AuditSearch */
        AuditSearch: {
            /** Account */
            account?: string | null;
            /** Client Ip */
            client_ip?: string | null;
            /** End At */
            end_at?: string | null;
            /** Event Id */
            event_id?: (4663 | 4660 | 4624) | null;
            /** File Id */
            file_id?: string | null;
            /**
             * Limit
             * @default 50
             */
            limit: number;
            /**
             * Offset
             * @default 0
             */
            offset: number;
            /** Sid */
            sid?: string | null;
            /** Source Id */
            source_id?: string | null;
            /** Start At */
            start_at?: string | null;
        };
        /** AuditStream */
        AuditStream: {
            /** Accepted At */
            accepted_at?: string | null;
            /** Collector Id */
            collector_id?: string | null;
            diagnostics?: components["schemas"]["AuditHealth"] | null;
            /**
             * Enabled
             * @default false
             */
            enabled: boolean;
            /**
             * Evaluated At
             * Format: date-time
             */
            evaluated_at: string;
            /** Reported At */
            reported_at?: string | null;
            /**
             * State
             * @enum {string}
             */
            state: "NOT_CONFIGURED" | "UNKNOWN" | "HEALTHY" | "STALE" | "GAP" | "ERROR" | "OBSERVE" | "BACKPRESSURE";
        };
        /** CapacitySummary */
        CapacitySummary: {
            /** Current Volume Count */
            current_volume_count: number;
            /** Free Bytes */
            free_bytes: number | null;
            /** Latest Inventory At */
            latest_inventory_at: string | null;
            /**
             * State
             * @enum {string}
             */
            state: "UNKNOWN" | "HEALTHY" | "OBSERVE" | "WARNING" | "CRITICAL";
            /** Total Bytes */
            total_bytes: number | null;
            /** Unavailable Volume Count */
            unavailable_volume_count: number;
            /** Used Bytes */
            used_bytes: number | null;
            /** Used Percent */
            used_percent: number | null;
            /** Volume Count */
            volume_count: number;
        };
        /** ChangeAudit */
        ChangeAudit: {
            actor: components["schemas"]["AuditActor"] | null;
            /** Candidates */
            candidates: components["schemas"]["AuditCandidateView"][];
            /**
             * Change Id
             * Format: uuid
             */
            change_id: string;
            /**
             * Classification
             * @enum {string}
             */
            classification: "CORRELATED_HIGH" | "ACCESS_OBSERVED" | "AMBIGUOUS" | "UNKNOWN" | "GAP" | "NOT_CONFIGURED";
            /** Object Id */
            object_id: string | null;
            /** Reason */
            reason: string;
            /** Rule Version */
            rule_version: string | null;
            stream: components["schemas"]["AuditStream"];
        };
        /** ClientObservation */
        ClientObservation: {
            /** Computer Guid */
            computer_guid?: string | null;
            /** Computer Name */
            computer_name?: string | null;
            /** Computer Sid */
            computer_sid?: string | null;
            /**
             * Event Time Confirmed
             * @default false
             * @constant
             */
            event_time_confirmed: false;
            /** Expires At */
            expires_at?: string | null;
            /** Observed At */
            observed_at?: string | null;
            /**
             * Provenance
             * @default DNS_PTR_FORWARD_AD_CURRENT
             * @constant
             */
            provenance: "DNS_PTR_FORWARD_AD_CURRENT";
            /** Ptr Name */
            ptr_name?: string | null;
            /** Reason */
            reason?: ("DNS_UNAVAILABLE" | "PTR_MISSING" | "FORWARD_MISMATCH" | "DOMAIN_MISMATCH" | "COMPUTER_MISSING" | "COMPUTER_DISABLED" | "MULTIPLE_MATCHES" | "LDAP_UNAVAILABLE" | "LOCAL_ADDRESS" | "LOOKUP_LIMIT") | null;
            /**
             * State
             * @enum {string}
             */
            state: "CONFIRMED_CURRENT" | "STALE" | "UNKNOWN" | "AMBIGUOUS";
            /**
             * Valid For Ms
             * @default 0
             */
            valid_for_ms: number;
        };
        /** CollectorCredential */
        CollectorCredential: {
            /**
             * Collector Type
             * @enum {string}
             */
            collector_type: "WINDOWS" | "AUDIT_WINDOWS" | "PVE" | "PBS";
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            directory_scope?: components["schemas"]["DirectoryScope"] | null;
            /** Enabled */
            enabled: boolean;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Last Seen At */
            last_seen_at: string | null;
            /**
             * Source Node Id
             * Format: uuid
             */
            source_node_id: string;
            /** Token */
            token: string;
            /** Version */
            version: string | null;
        };
        /** CollectorView */
        CollectorView: {
            /**
             * Collector Type
             * @enum {string}
             */
            collector_type: "WINDOWS" | "AUDIT_WINDOWS" | "PVE" | "PBS";
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            directory_scope?: components["schemas"]["DirectoryScope"] | null;
            /** Enabled */
            enabled: boolean;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Last Seen At */
            last_seen_at: string | null;
            /**
             * Source Node Id
             * Format: uuid
             */
            source_node_id: string;
            /** Version */
            version: string | null;
        };
        /** Counts */
        Counts: {
            /** Filesystem Objects */
            filesystem_objects: number;
            /** Shares */
            shares: number;
            /** Sources */
            sources: number;
            /** Volumes */
            volumes: number;
        };
        /** CreateCollector */
        CreateCollector: {
            /**
             * Collector Type
             * @enum {string}
             */
            collector_type: "WINDOWS" | "AUDIT_WINDOWS" | "PVE" | "PBS";
            directory_scope?: components["schemas"]["DirectoryScope"] | null;
        };
        /** CreateSource */
        CreateSource: {
            /**
             * Expected Cadence Seconds
             * @default 60
             */
            expected_cadence_seconds: number;
            /** Fqdn */
            fqdn?: string | null;
            /** Hostname */
            hostname: string;
            /** Instance Id */
            instance_id: string;
            /**
             * Source Type
             * @enum {string}
             */
            source_type: "FILESERVER" | "PVE" | "PBS";
        };
        /** DirectoryScope */
        DirectoryScope: {
            /** Dns Domain */
            dns_domain: string;
            /** Domain Sid */
            domain_sid: string;
        };
        /** DirectoryStream */
        DirectoryStream: {
            /** Error Code */
            error_code?: ("LDAP_UNAVAILABLE" | "DIRECTORY_LIMIT" | "DIRECTORY_STOPPED") | null;
            /**
             * Evaluated At
             * Format: date-time
             */
            evaluated_at: string;
            /** Latest Attempt At */
            latest_attempt_at?: string | null;
            /** Observed At */
            observed_at?: string | null;
            scope?: components["schemas"]["DirectoryScope"] | null;
            /**
             * State
             * @enum {string}
             */
            state: "NOT_CONFIGURED" | "CURRENT" | "STALE" | "UNKNOWN" | "PARTIAL" | "ERROR";
            /** User Count */
            user_count?: number | null;
            /**
             * Valid For Ms
             * @default 0
             */
            valid_for_ms: number;
        };
        /** DirectoryUser */
        DirectoryUser: {
            /** Account */
            account: string;
            /** Display Name */
            display_name?: string | null;
            /** Enabled */
            enabled: boolean;
            /**
             * Object Guid
             * Format: uuid
             */
            object_guid: string;
            /** Primary Group Id */
            primary_group_id: number;
            /** Sid */
            sid: string;
            /** Upn */
            upn?: string | null;
        };
        /** DomainHealth */
        DomainHealth: {
            /** Covered Source Count */
            covered_source_count: number;
            /** Domain */
            domain: string;
            /** Source Count */
            source_count: number;
            /**
             * State
             * @enum {string}
             */
            state: "HEALTHY" | "OBSERVE" | "WARNING" | "CRITICAL" | "UNKNOWN" | "NOT_APPLICABLE";
            /** Unknown Source Count */
            unknown_source_count: number;
        };
        /** Domains */
        Domains: {
            /** Domains */
            domains: components["schemas"]["DomainHealth"][];
            /**
             * Evaluated At
             * Format: date-time
             */
            evaluated_at: string;
        };
        /** Freshness */
        Freshness: {
            /** Age Seconds */
            age_seconds: number | null;
            /** Bottleneck Collector Id */
            bottleneck_collector_id: string | null;
            /** Collector Count */
            collector_count: number;
            /** Cursor */
            cursor: string | null;
            /** Expected Cadence Seconds */
            expected_cadence_seconds: number;
            /** Lag Seconds */
            lag_seconds: number | null;
            /** Last Collector At */
            last_collector_at: string | null;
            /** Last Event At */
            last_event_at: string | null;
            /** Last Success At */
            last_success_at: string | null;
            /** Reason */
            reason: string;
            /**
             * State
             * @enum {string}
             */
            state: "HEALTHY" | "OBSERVE" | "WARNING" | "CRITICAL" | "UNKNOWN" | "NOT_APPLICABLE";
            /** Unknown Collector Count */
            unknown_collector_count: number;
        };
        /** FreshnessSummary */
        FreshnessSummary: {
            /** Current Source Count */
            current_source_count: number;
            /** Last Received At */
            last_received_at: string | null;
            /** Oldest Event At */
            oldest_event_at: string | null;
            /** Source Count */
            source_count: number;
            /** Stale Source Count */
            stale_source_count: number;
            /**
             * State
             * @enum {string}
             */
            state: "HEALTHY" | "OBSERVE" | "WARNING" | "CRITICAL" | "UNKNOWN" | "NOT_APPLICABLE";
            /** Unknown Source Count */
            unknown_source_count: number;
        };
        /** InventorySummary */
        InventorySummary: {
            /** Filesystem Objects */
            filesystem_objects: number;
            /** Filesystem Types */
            filesystem_types: string[];
            /** Latest Inventory At */
            latest_inventory_at: string | null;
            /** Volume Count */
            volume_count: number;
        };
        /** LoginRequest */
        LoginRequest: {
            /**
             * Password
             * Format: password
             */
            password: string;
            /**
             * Provider
             * @enum {string}
             */
            provider: "local" | "ldap";
            /** Username */
            username: string;
        };
        /** Overview */
        Overview: {
            capacity: components["schemas"]["CapacitySummary"];
            counts: components["schemas"]["Counts"];
            /** Domains */
            domains: components["schemas"]["DomainHealth"][];
            /**
             * Evaluated At
             * Format: date-time
             */
            evaluated_at: string;
            freshness: components["schemas"]["FreshnessSummary"];
            inventory: components["schemas"]["InventorySummary"];
            /**
             * Overall State
             * @enum {string}
             */
            overall_state: "HEALTHY" | "OBSERVE" | "WARNING" | "CRITICAL" | "UNKNOWN" | "NOT_APPLICABLE";
        };
        /** Page[CollectorView] */
        Page_CollectorView_: {
            /** Items */
            items: components["schemas"]["CollectorView"][];
            /** Limit */
            limit: number;
            /** Offset */
            offset: number;
            /** Total */
            total: number;
        };
        /** Page[Share] */
        Page_Share_: {
            /** Items */
            items: components["schemas"]["Share"][];
            /** Limit */
            limit: number;
            /** Offset */
            offset: number;
            /** Total */
            total: number;
        };
        /** Page[Source] */
        Page_Source_: {
            /** Items */
            items: components["schemas"]["Source"][];
            /** Limit */
            limit: number;
            /** Offset */
            offset: number;
            /** Total */
            total: number;
        };
        /** Page[Volume] */
        Page_Volume_: {
            /** Items */
            items: components["schemas"]["Volume"][];
            /** Limit */
            limit: number;
            /** Offset */
            offset: number;
            /** Total */
            total: number;
        };
        /** RotateCollector */
        RotateCollector: Record<string, never>;
        /** SetCollectorEnabled */
        SetCollectorEnabled: {
            /** Enabled */
            enabled: boolean;
        };
        /** Share */
        Share: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Last Seen At
             * Format: date-time
             */
            last_seen_at: string;
            /** Name */
            name: string;
            /** Protocol */
            protocol: string;
            /**
             * Quality
             * @enum {string}
             */
            quality: "COMPLETE" | "PARTIAL" | "STALE" | "ESTIMATED" | "UNAVAILABLE";
            /** Relative Path */
            relative_path: string;
            /**
             * Source Node Id
             * Format: uuid
             */
            source_node_id: string;
            /** Volume Id */
            volume_id: string | null;
        };
        /** Source */
        Source: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Fqdn */
            fqdn: string | null;
            freshness: components["schemas"]["Freshness"];
            /** Hostname */
            hostname: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Instance Id */
            instance_id: string;
            /**
             * Source Type
             * @enum {string}
             */
            source_type: "FILESERVER" | "PVE" | "PBS";
        };
        /** SourceRegistration */
        SourceRegistration: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Expected Cadence Seconds
             * @default 60
             */
            expected_cadence_seconds: number;
            /** Fqdn */
            fqdn?: string | null;
            /** Hostname */
            hostname: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Instance Id */
            instance_id: string;
            /**
             * Source Type
             * @enum {string}
             */
            source_type: "FILESERVER" | "PVE" | "PBS";
        };
        /** UserResponse */
        UserResponse: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Roles */
            roles: ("storage_admin" | "storage_operator" | "auditor" | "analyst" | "viewer")[];
            /** Username */
            username: string;
        };
        /** Volume */
        Volume: {
            /** Filesystem */
            filesystem: string;
            /**
             * First Seen At
             * Format: date-time
             */
            first_seen_at: string;
            /** Free Bytes */
            free_bytes: number | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Label */
            label: string | null;
            /**
             * Last Seen At
             * Format: date-time
             */
            last_seen_at: string;
            /** Mount Aliases */
            mount_aliases: string[];
            /**
             * Quality
             * @enum {string}
             */
            quality: "COMPLETE" | "PARTIAL" | "STALE" | "ESTIMATED" | "UNAVAILABLE";
            /**
             * Source Node Id
             * Format: uuid
             */
            source_node_id: string;
            /** Total Bytes */
            total_bytes: number | null;
            /** Unique Identity */
            unique_identity: string;
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    activity_api_v1_activity_get: {
        parameters: {
            query?: {
                limit?: number;
                offset?: number;
                source_id?: string | null;
                event_type?: ("CREATE" | "WRITE" | "RENAME" | "DELETE" | "METADATA_CHANGE" | "SECURITY_CHANGE") | null;
                start_at?: string | null;
                end_at?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    "Cache-Control"?: "no-store";
                    /** @description Relative evidence lifetime from snapshot time; clients subtract complete request elapsed time. */
                    "X-Evidence-Valid-For-Ms"?: number;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Activity"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Unprocessable Content */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
        };
    };
    evidence_api_v1_audit_changes__change_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                change_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ChangeAudit"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Content Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Unprocessable Content */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
        };
    };
    object_identity_api_v1_audit_objects__object_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                object_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AuditObject"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Content Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Unprocessable Content */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
        };
    };
    search_api_v1_audit_search_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AuditSearch"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AuditPage"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Content Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Unprocessable Content */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
        };
    };
    status_api_v1_audit_sources__source_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                source_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AuditStream"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Content Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Unprocessable Content */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
        };
    };
    directory_status_api_v1_audit_sources__source_id__directory_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                source_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DirectoryStream"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Content Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Unprocessable Content */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
        };
    };
    login_api_v1_auth_login_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LoginRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UserResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Content Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Unprocessable Content */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
        };
    };
    logout_api_v1_auth_logout_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
        };
    };
    me_api_v1_auth_me_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UserResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
        };
    };
    enable_api_v1_collectors__collector_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                collector_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SetCollectorEnabled"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CollectorView"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Content Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Unprocessable Content */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
        };
    };
    rotate_api_v1_collectors__collector_id__rotate_token_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                collector_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RotateCollector"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CollectorCredential"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Content Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Unprocessable Content */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
        };
    };
    health_domains_api_v1_health_domains_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    "Cache-Control"?: "no-store";
                    /** @description Relative evidence lifetime from snapshot time; clients subtract complete request elapsed time. */
                    "X-Evidence-Valid-For-Ms"?: number;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Domains"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Unprocessable Content */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
        };
    };
    overview_api_v1_overview_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    "Cache-Control"?: "no-store";
                    /** @description Relative evidence lifetime from snapshot time; clients subtract complete request elapsed time. */
                    "X-Evidence-Valid-For-Ms"?: number;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Overview"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Unprocessable Content */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
        };
    };
    share_list_api_v1_shares_get: {
        parameters: {
            query?: {
                limit?: number;
                offset?: number;
                source_id?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    "Cache-Control"?: "no-store";
                    /** @description Relative evidence lifetime from snapshot time; clients subtract complete request elapsed time. */
                    "X-Evidence-Valid-For-Ms"?: number;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Page_Share_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Unprocessable Content */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
        };
    };
    sources_api_v1_sources_get: {
        parameters: {
            query?: {
                limit?: number;
                offset?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    "Cache-Control"?: "no-store";
                    /** @description Relative evidence lifetime from snapshot time; clients subtract complete request elapsed time. */
                    "X-Evidence-Valid-For-Ms"?: number;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Page_Source_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Unprocessable Content */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
        };
    };
    register_api_v1_sources_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateSource"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SourceRegistration"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Content Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Unprocessable Content */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
        };
    };
    source_detail_api_v1_sources__source_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                source_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    "Cache-Control"?: "no-store";
                    /** @description Relative evidence lifetime from snapshot time; clients subtract complete request elapsed time. */
                    "X-Evidence-Valid-For-Ms"?: number;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Source"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Unprocessable Content */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
        };
    };
    list_collectors_api_v1_sources__source_id__collectors_get: {
        parameters: {
            query?: {
                limit?: number;
                offset?: number;
            };
            header?: never;
            path: {
                source_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Page_CollectorView_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Content Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Unprocessable Content */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
        };
    };
    enroll_api_v1_sources__source_id__collectors_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                source_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateCollector"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CollectorCredential"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Content Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Unprocessable Content */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
        };
    };
    source_freshness_api_v1_sources__source_id__freshness_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                source_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    "Cache-Control"?: "no-store";
                    /** @description Relative evidence lifetime from snapshot time; clients subtract complete request elapsed time. */
                    "X-Evidence-Valid-For-Ms"?: number;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Freshness"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Unprocessable Content */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
        };
    };
    volume_list_api_v1_volumes_get: {
        parameters: {
            query?: {
                limit?: number;
                offset?: number;
                source_id?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    "Cache-Control"?: "no-store";
                    /** @description Relative evidence lifetime from snapshot time; clients subtract complete request elapsed time. */
                    "X-Evidence-Valid-For-Ms"?: number;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Page_Volume_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Unprocessable Content */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
        };
    };
}
