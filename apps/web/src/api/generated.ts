export interface paths {
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
        post?: never;
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
        /** ApiError */
        ApiError: {
            /** Detail */
            detail: string;
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
        /** Overview */
        Overview: {
            counts: components["schemas"]["Counts"];
            /** Domains */
            domains: components["schemas"]["DomainHealth"][];
            /**
             * Evaluated At
             * Format: date-time
             */
            evaluated_at: string;
            freshness: components["schemas"]["FreshnessSummary"];
            /**
             * Overall State
             * @enum {string}
             */
            overall_state: "HEALTHY" | "OBSERVE" | "WARNING" | "CRITICAL" | "UNKNOWN" | "NOT_APPLICABLE";
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
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Domains"];
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
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Overview"];
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
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Page_Share_"];
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
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Page_Source_"];
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
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Source"];
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
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Freshness"];
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
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Page_Volume_"];
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
