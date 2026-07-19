export interface TextContent {
  role_definition?: string;
  goal?: string;
  workflow?: string;
  behavior_constraints?: string;
  background?: string;
}

export interface AssetRequired {
  type: string;
  query: string;
}

export type ResourceType = 'datasource' | 'mcp' | 'knowledge' | 'app' | 'llm_model';

export interface Resource {
  type: ResourceType;
  ref: string;
}

export interface DeliveryChannel {
  category: string;
  channel: string;
  target: string;
  format?: string;
  require_intervention?: string;
}

export interface Deliverable {
  type: string;
  title?: string;
  delivery: DeliveryChannel[];
}

export interface DistillProduce {
  type: string;
  from: string;
  when?: string;
}

export interface DistillConfig {
  forced: boolean;
  produce: DistillProduce[];
}

export type SkillRef = string | { type: string; name: string };

export interface PlaybookContext {
  assets_required?: AssetRequired[];
  resources?: Resource[];
}

export interface PlaybookDeclaration {
  text_content?: TextContent;
  skills?: SkillRef[];
  context?: PlaybookContext;
  deliverables?: Deliverable[];
  distill?: DistillConfig;
}

export interface ResourceItem {
  key: string;
  name: string;
  label?: string;
  description?: string;
  type?: string;
  [key: string]: any;
}
