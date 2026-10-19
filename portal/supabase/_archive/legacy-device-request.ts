/**
 * device-request
 * Version: 2.0.0 | Updated: 2026-06-25
 * Changelog:
 *   2.0.0 — Switched from random code (XXXX-XXXX) to permanent device_id (UUID)
 *           Upserts on conflict so re-registration resets to pending cleanly
 *   1.0.0 — Initial release with random code generation
 *
 * Called by the local NeuralOps app on boot.
 * Accepts a permanent device_id (UUID) from the caller instead of generating a random code.
 * Requires: anon key + X-NeuralOps-Token (install secret)
 */

import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

Deno.serve(async (req) => {
  // Verify install token
  const installToken = req.headers.get('x-neuralops-token')
  if (installToken !== Deno.env.get('NEURALOPS_INSTALL_TOKEN')) {
    return new Response(
      JSON.stringify({ error: 'Forbidden' }),
      { status: 403, headers: { 'Content-Type': 'application/json' } }
    )
  }

  const supabase = createClient(
    Deno.env.get('SUPABASE_URL')!,
    Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!,
  )

  const body = await req.json().catch(() => ({}))
  const deviceId = body.device_id
  const deviceName = body.device_name || 'Unknown Device'
  const deviceIp = req.headers.get('x-forwarded-for') || null

  if (!deviceId) {
    return new Response(
      JSON.stringify({ error: 'device_id is required' }),
      { status: 400, headers: { 'Content-Type': 'application/json' } }
    )
  }

  // Upsert — if device_id already exists (re-registration), reset it to pending
  const { error } = await supabase
    .from('device_codes')
    .upsert({
      device_id: deviceId,
      device_name: deviceName,
      device_ip: deviceIp,
      status: 'pending',
      user_id: null,
      user_email: null,
      verified_at: null,
    }, { onConflict: 'device_id' })

  if (error) {
    return new Response(
      JSON.stringify({ error: 'Failed to register device' }),
      { status: 500, headers: { 'Content-Type': 'application/json' } }
    )
  }

  return new Response(
    JSON.stringify({ device_id: deviceId, status: 'pending' }),
    { status: 200, headers: { 'Content-Type': 'application/json' } }
  )
})
