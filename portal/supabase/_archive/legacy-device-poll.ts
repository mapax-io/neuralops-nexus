/**
 * device-poll
 * Version: 2.1.0 | Updated: 2026-06-25
 * Changelog:
 *   2.1.0 — Returns session_expires_at in active response
 *           Returns session_expired status if session has passed
 *   2.0.0 — Switched lookup from temporary code to permanent device_id (UUID)
 *   1.0.0 — Initial release with code-based lookup
 *
 * Called by the local NeuralOps app every 3 seconds.
 * Looks up by device_id (permanent UUID) instead of temporary code.
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

  const url = new URL(req.url)
  const deviceId = url.searchParams.get('device_id')

  if (!deviceId) {
    return new Response(
      JSON.stringify({ error: 'device_id is required' }),
      { status: 400, headers: { 'Content-Type': 'application/json' } }
    )
  }

  const supabase = createClient(
    Deno.env.get('SUPABASE_URL')!,
    Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!,
  )

  const { data: device } = await supabase
    .from('device_codes')
    .select('*')
    .eq('device_id', deviceId)
    .single()

  if (!device) {
    return new Response(
      JSON.stringify({ status: 'not_found' }),
      { status: 404, headers: { 'Content-Type': 'application/json' } }
    )
  }

  if (device.status === 'revoked') {
    return new Response(
      JSON.stringify({ status: 'revoked' }),
      { status: 200, headers: { 'Content-Type': 'application/json' } }
    )
  }

  if (device.status === 'pending') {
    return new Response(
      JSON.stringify({ status: 'pending' }),
      { status: 200, headers: { 'Content-Type': 'application/json' } }
    )
  }

  // Check if session has expired
  if (device.session_expires_at && new Date(device.session_expires_at) < new Date()) {
    return new Response(
      JSON.stringify({ status: 'session_expired' }),
      { status: 200, headers: { 'Content-Type': 'application/json' } }
    )
  }

  // Active — update last_used_at and return identity
  await supabase
    .from('device_codes')
    .update({ last_used_at: new Date().toISOString() })
    .eq('device_id', deviceId)

  return new Response(
    JSON.stringify({
      status: 'active',
      email: device.user_email,
      user_id: device.user_id,
      device_name: device.device_name,
      session_expires_at: device.session_expires_at,
    }),
    { status: 200, headers: { 'Content-Type': 'application/json' } }
  )
})
