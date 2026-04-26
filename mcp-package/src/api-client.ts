interface VersionFileOut {
  id: string;
  path: string;
  file_type: string;
  mime_type?: string;
  encoding?: string;
  size_bytes: number;
}

interface VersionFileDetailOut extends VersionFileOut {
  content: string | null;
  content_base64: string | null;
}

export type RiskLevel = "low" | "medium" | "high" | "critical";

export interface KoinoflowMetadata {
  retrieval_keywords?: string[];
  risk_level?: RiskLevel | null;
  requires_human_approval?: boolean;
  prerequisites?: string[];
  audience?: string[];
}

interface SkillVersionOut {
  id?: string;
  version_number: number;
  content_md: string;
  frontmatter_yaml: string;
  change_summary: string;
  files?: VersionFileOut[];
  koinoflow_metadata?: KoinoflowMetadata;
}

export interface SkillDetail {
  id: string;
  title: string;
  slug: string;
  description: string;
  status: string;
  current_version: SkillVersionOut | null;
}

export interface SkillListItem {
  title: string;
  slug: string;
  description: string;
  current_version_number: number | null;
  department_name: string;
  team_name: string;
  risk_level?: RiskLevel | null;
  retrieval_keywords?: string[];
  requires_human_approval?: boolean;
}

export interface SkillListResponse {
  items: SkillListItem[];
  count: number;
}

export interface SkillDiscoveryItem {
  id: string;
  title: string;
  slug: string;
  description: string;
  department_name: string;
  team_name: string;
  current_version_number: number | null;
  risk_level?: RiskLevel | null;
  retrieval_keywords?: string[];
  requires_human_approval?: boolean;
  score: number;
  vector_score: number | null;
  lexical_score: number;
  match_reasons: string[];
  snippet: string;
  indexed: boolean;
}

export interface SkillDiscoveryResponse {
  items: SkillDiscoveryItem[];
  count: number;
  embedding_status: string;
}

export class KoinoflowAPIClient {
  private baseUrl: string;
  private apiKey: string;

  constructor(baseUrl: string, apiKey: string) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.apiKey = apiKey;
  }

  private async request<T>(
    path: string,
    params?: Record<string, string>,
  ): Promise<T> {
    const url = new URL(`${this.baseUrl}${path}`);
    if (params) {
      for (const [k, v] of Object.entries(params)) {
        if (v) url.searchParams.set(k, v);
      }
    }

    const response = await fetch(url.toString(), {
      headers: { Authorization: `Bearer ${this.apiKey}` },
    });

    if (!response.ok) {
      throw new Error(`API error ${response.status}: ${await response.text()}`);
    }

    return response.json() as Promise<T>;
  }

  async getSkill(
    slug: string,
    version?: number,
  ): Promise<SkillDetail | SkillVersionOut> {
    const path =
      version !== undefined
        ? `/skills/${slug}/versions/${version}`
        : `/skills/${slug}`;
    return this.request<SkillDetail | SkillVersionOut>(path);
  }

  async getSkillFile(
    slug: string,
    version: number,
    path: string,
  ): Promise<VersionFileDetailOut> {
    return this.request<VersionFileDetailOut>(
      `/skills/${slug}/versions/${version}/files/${encodeURIComponent(path)}`,
    );
  }

  async listSkills(
    department?: string,
    team?: string,
    search?: string,
    limit: number = 100,
    offset: number = 0,
  ): Promise<SkillListResponse> {
    const params: Record<string, string> = {
      status: "published",
      limit: String(Math.min(Math.max(limit, 1), 100)),
      offset: String(offset),
    };
    if (department) params.department = department;
    if (team) params.team = team;
    if (search) params.search = search;
    return this.request<SkillListResponse>("/skills", params);
  }

  async discoverSkills(
    query: string,
    department?: string,
    team?: string,
    limit: number = 10,
  ): Promise<SkillDiscoveryResponse> {
    const params: Record<string, string> = {
      query,
      limit: String(Math.min(Math.max(limit, 1), 25)),
    };
    if (department) params.department = department;
    if (team) params.team = team;
    return this.request<SkillDiscoveryResponse>("/skills/discover", params);
  }

  async logUsage(
    skillId: string,
    versionNumber: number,
    clientId: string,
    clientType: string,
  ): Promise<void> {
    try {
      await fetch(`${this.baseUrl}/usage`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${this.apiKey}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          skill_id: skillId,
          version_number: versionNumber,
          client_id: clientId,
          client_type: clientType,
        }),
      });
    } catch {
      // Fire and forget — don't break the tool on usage logging failure
    }
  }

  async createSkillVersion(
    slug: string,
    payload: {
      content_md: string;
      frontmatter_yaml: string;
      change_summary: string;
    },
  ): Promise<SkillVersionOut> {
    const response = await fetch(`${this.baseUrl}/processes/${slug}/versions`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${this.apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      throw new Error(`API error ${response.status}: ${await response.text()}`);
    }

    return (await response.json()) as SkillVersionOut;
  }
}
