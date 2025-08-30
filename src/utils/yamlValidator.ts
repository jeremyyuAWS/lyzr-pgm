import yaml from "js-yaml";

interface AgentDefinition {
  name: string;
  description: string;
  agent_role: string;
  agent_goal: string;
  agent_instructions: string;
  features: any[];
  tools: any[];
  response_format: {
    type: string;
  };
}

interface UseCaseFile {
  use_cases: {
    name: string;
    description: string;
  }[];
}

export function validateYaml(content: string): {
  valid: boolean;
  errors?: string[];
  parsed?: any;
} {
  try {
    // Parse YAML into JS object
    const parsed = yaml.load(content);

    if (!parsed) {
      return { valid: false, errors: ["Empty YAML content"] };
    }

    const errors: string[] = [];

    // Detect if it's a Use Case YAML or Agent YAML
    if ("use_cases" in (parsed as any)) {
      const ucFile = parsed as UseCaseFile;
      if (!Array.isArray(ucFile.use_cases)) {
        errors.push("`use_cases` must be an array");
      } else {
        ucFile.use_cases.forEach((uc, idx) => {
          if (!uc.name) errors.push(`Use case #${idx + 1} missing 'name'`);
          if (!uc.description) errors.push(`Use case #${idx + 1} missing 'description'`);
        });
      }
    } else {
      // Assume it's an Agent YAML
      const agent = parsed as AgentDefinition;

      ["name", "description", "agent_role", "agent_goal", "agent_instructions"].forEach((key) => {
        if (!(agent as any)[key]) {
          errors.push(`Missing required field: ${key}`);
        }
      });

      if (!agent.response_format?.type) {
        errors.push("Missing required field: response_format.type");
      }
    }

    return {
      valid: errors.length === 0,
      errors: errors.length > 0 ? errors : undefined,
      parsed,
    };
  } catch (err: any) {
    return { valid: false, errors: [`YAML parse error: ${err.message}`] };
  }
}
