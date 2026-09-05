"""
Split the stored LiteLLM model string into provider + bare model name.

LiteLLM addresses a model as "provider/model"; pydantic-ai uses
"provider:model". Rather than store a combined string in either dialect --
and rewrite every row the next time a dependency changes its separator --
provider and the bare name are now two columns, and ModelConfig.qualified_id
composes the wire format at the boundary.

    before:  provider="litellm"    model_id="anthropic/claude-haiku-4-5-20251001"
    after:   provider="anthropic"  model_id="claude-haiku-4-5-20251001"
             qualified_id -> "anthropic:claude-haiku-4-5-20251001"

Vendors without a first-class pydantic-ai provider collapse into
"openai_compatible" -- they are all reachable with an OpenAI-shaped API
plus an api_base, and are constructed identically. Anything unmapped is
REPORTED, not mangled: a wrong guess here silently repoints a persona at a
different model, which is far worse than a row a human has to look at.
"""
from django.db import migrations

_LITELLM_VENDOR_TO_PROVIDER = {
    # native pydantic-ai providers
    'anthropic':     'anthropic',
    'openai':        'openai',
    'gemini':        'google',
    'google':        'google',
    'vertex_ai':     'google',
    'ollama':        'ollama',
    # OpenAI-shaped -- one construction path, no separate enum member
    'azure':             'openai_compatible',
    'mistral':           'openai_compatible',
    'deepseek':          'openai_compatible',
    'groq':              'openai_compatible',
    'together_ai':       'openai_compatible',
    'openrouter':        'openai_compatible',
    'fireworks_ai':      'openai_compatible',
    'perplexity':        'openai_compatible',
    'xai':               'openai_compatible',
    'openai_compatible': 'openai_compatible',
}


def _split(raw: str):
    """Return (provider, bare_model) or None if it cannot be mapped."""
    raw = (raw or '').strip()
    if not raw:
        return None
    # tolerate a value already in pydantic-ai form
    sep = '/' if '/' in raw else (':' if ':' in raw else None)
    if sep is None:
        return None
    vendor, _, rest = raw.partition(sep)
    provider = _LITELLM_VENDOR_TO_PROVIDER.get(vendor.strip().lower())
    if not provider or not rest.strip():
        return None
    return provider, rest.strip()


def forwards(apps, schema_editor):
    ModelConfig = apps.get_model('nucleus', 'ModelConfig')
    CompanyAIConfig = apps.get_model('nucleus', 'CompanyAIConfig')

    converted, unmapped = 0, []
    for cfg in ModelConfig.objects.all().iterator():
        split = _split(cfg.model_id)
        if split is None:
            unmapped.append((str(cfg.pk), cfg.name, cfg.provider, cfg.model_id))
            continue
        cfg.provider, cfg.model_id = split
        cfg.save(update_fields=['provider', 'model_id'])
        converted += 1

    print("[0014] converted %d ModelConfig row(s)" % converted)

    if unmapped:
        print(
            "\n[0014] ==================== NEEDS MANUAL REVIEW ====================\n"
            "[0014] %d ModelConfig row(s) could not be split automatically.\n"
            "[0014] They keep their existing provider/model_id and WILL NOT WORK\n"
            "[0014] until corrected -- qualified_id would produce nonsense.\n"
            "[0014] (pk, name, provider, model_id):\n"
            "[0014]   %s\n"
            "[0014] Fix with:  UPDATE intelligence_model_config\n"
            "[0014]              SET provider='anthropic', model_id='claude-...'\n"
            "[0014]            WHERE id='...';\n"
            "[0014] =============================================================\n"
            % (len(unmapped), '\n[0014]   '.join(map(str, unmapped)))
        )

    # CompanyAIConfig.default_llm_model is a plain string, not an FK.
    for company_cfg in CompanyAIConfig.objects.all().iterator():
        split = _split(company_cfg.default_llm_model)
        if split is None:
            continue
        provider, bare = split
        new_value = "%s:%s" % (provider, bare)
        if new_value != company_cfg.default_llm_model:
            company_cfg.default_llm_model = new_value
            company_cfg.save(update_fields=['default_llm_model'])


def backwards(apps, schema_editor):
    """
    Rejoin provider and model_id with a slash. Lossy: everything that
    collapsed into openai_compatible comes back as that literal vendor
    prefix, which LiteLLM would not recognise. Present so the migration is
    technically reversible, not because reversing is a good idea.
    """
    ModelConfig = apps.get_model('nucleus', 'ModelConfig')
    for cfg in ModelConfig.objects.all().iterator():
        if '/' in (cfg.model_id or ''):
            continue
        cfg.model_id = "%s/%s" % (cfg.provider, cfg.model_id)
        cfg.provider = 'litellm'
        cfg.save(update_fields=['provider', 'model_id'])


class Migration(migrations.Migration):

    dependencies = [
        ('nucleus', '0013_rename_aimodel_to_modelconfig'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
