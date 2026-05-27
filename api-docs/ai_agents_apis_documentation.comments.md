All agent/model get, delete, patch and post endpoints must adhere to the following schema, the json outputs of each response, and the associated schemas will need to be updated.

```python
class ModelSchema(Schema):
    id: str # A unique model identifier
    provider: str | None # A list of officially supported providers will be exposed through a nexus-ai endpoint. In case a provider is named, an endpoint_url is not required
    endpoint_url: str | None # Required for custom or unknown model providers. Required if a provider is not specified
    api_key: str # API key required for model auth
    model_name: str # Model name 
    temperature: float # Model temperature, between 0 and 1 

class MCPServerSchema(Schema):
    id: UUID 
    name: str
    server_type: str
    transport: str
    url: Optional[str]
    
class AgentSchema(Schema):
    id: str # A unique agent identifier
    name: str # A human friendly identifier
    model: ModelSchema # The associated model attached to the agent 
    description: str # an optional description for the agent
    agent_type: Enum[Internal, External] # Agent scope
    created_at: datetime # Agent creation
    updated_at: datetime # Agent update 
    system_prompt: str #  The foundational instructions, persona, and rules the agent must follow
    tools: list[str] # list of tools (python functions) that the model is allowed to call
    mcp_servers: list[MCPServerSchema] # MCP server schema will be specified later, can be left blank at the moment
    dependencies: Dict # state/context like user IDs, database connections, or current application state
    max_retries: int # retries for if the LLM hallucinates a bad tool call or wrong output schema
    max_history_messages: int # Context cut off length
    max_steps: int # Decides how many steps an agent is allotted 
    context_window_strategy: str # Context trimming strategy
    timeout_seconds: int # Agent time out
    max_tool_calls_per_run: int # Maxmimum number of tool calls the agent is allowd
    is_active: bool # Flag to decide whether the agent is active or not
    safety_mode: bool # Toggles safety mode


    
```
