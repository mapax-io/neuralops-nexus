/**
 * device-verify
 * Version: 2.1.0 | Updated: 2026-06-25
 * Changelog:
 *   2.1.0 — Added session_expires_at (30 days) set on activation
 *   2.0.0 — Switched from typed code (XXXX-XXXX) to permanent device_id (UUID)
 *           Auto-called by portal after login — user never types anything
 *           ALLOWED_ORIGIN enforcement retained
 *   1.1.0 — Added ALLOWED_ORIGIN origin check
 *   1.0.0 — Initial release
 *
 * Called by the portal immediately after user logs in.
 * Requires: valid Supabase user JWT
 */

import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

Deno.serve(async (req) => {
  // Build CORS headers — restrict to ALLOWED_ORIGIN in production, allow all in dev
  const allowedOrigin = Deno.env.get('ALLOWED_ORIGIN') ?? '*'
  const corsHeaders = {
    'Access-Control-Allow-Origin': allowedOrigin,
    'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
  }

  // Handle CORS preflight
  if (req.method === 'OPTIONS') {
    return new Response(null, { status: 204, headers: corsHeaders })
  }

  // Enforce origin in production
  if (allowedOrigin !== '*') {
    const origin = req.headers.get('origin') ?? ''
    if (origin !== allowedOrigin) {
      return new Response(
        JSON.stringify({ error: 'Forbidden' }),
        { status: 403, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }
  }

  const authHeader = req.headers.get('Authorization')
  if (!authHeader) {
    return new Response(
      JSON.stringify({ error: 'Unauthorized' }),
      { status: 401, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    )
  }

  const { device_id } = await req.json()
  if (!device_id) {
    return new Response(
      JSON.stringify({ error: 'device_id is required' }),
      { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    )
  }

  const supabase = createClient(
    Deno.env.get('SUPABASE_URL')!,
    Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!,
  )

  const token = authHeader.replace('Bearer ', '')
  const { data: { user }, error: userError } = await supabase.auth.getUser(token)
  if (userError || !user) {
    return new Response(
      JSON.stringify({ error: 'Invalid session' }),
      { status: 401, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    )
  }

  const { data: device, error: deviceError } = await supabase
    .from('device_codes')
    .select('*')
    .eq('device_id', device_id)
    .eq('status', 'pending')
    .single()

  if (deviceError || !device) {
    return new Response(
      JSON.stringify({ error: 'Device not found or already activated' }),
      { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    )
  }

  // Session lasts 30 days from activation
  const sessionExpiresAt = new Date(Date.now() + 30 * 24 * 60 * 60 * 1000)

  const { error: updateError } = await supabase
    .from('device_codes')
    .update({
      user_id: user.id,
      user_email: user.email,
      status: 'active',
      verified_at: new Date().toISOString(),
      last_used_at: new Date().toISOString(),
      session_expires_at: sessionExpiresAt.toISOString(),
    })
    .eq('device_id', device_id)

  if (updateError) {
    return new Response(
      JSON.stringify({ error: 'Failed to activate device' }),
      { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    )
  }

  return new Response(
    JSON.stringify({
      success: true,
      device_name: device.device_name,
      session_expires_at: sessionExpiresAt.toISOString(),
    }),
    { status: 200, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
  )
})
