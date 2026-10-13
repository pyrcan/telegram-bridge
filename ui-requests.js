import { useCallback, useEffect, useMemo } from 'react'

// One bounded request owner for this mounted app identity. No retries: a timed
// out write can already have been accepted by the server.
export function useBoundedRequests(appId, token) {
  const session = useMemo(() => ({ active: true, controllers: new Set() }), [appId, token])
  useEffect(() => {
    session.active = true
    return () => {
      session.active = false
      for (const controller of session.controllers) controller.abort()
    }
  }, [session])
  return useCallback(async (path, options = {}) => {
    if (!session.active) throw new DOMException('Retired app read', 'AbortError')
    const controller = new AbortController()
    session.controllers.add(controller)
    let timedOut = false
    const timer = setTimeout(() => { timedOut = true; controller.abort() }, 12000)
    try {
      const response = await fetch(path, { ...options, signal: controller.signal })
      // Keep the deadline through body consumption, not merely response headers.
      const value = options.method === 'HEAD' || response.status === 204
        ? null
        : response.ok || response.status === 404 ? await response.json() : null
      if (!session.active) throw new DOMException('Retired app read', 'AbortError')
      return { ok: response.ok, status: response.status, json: async () => value }
    } catch (error) {
      if (timedOut) throw new Error('The request took too long. Try again when connected.')
      throw error
    } finally {
      clearTimeout(timer)
      session.controllers.delete(controller)
    }
  }, [session])
}

export async function boundedStorageRead(read) {
  let timer
  try {
    return await Promise.race([
      read(),
      new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error('Saved settings could not be read.')), 12000)
      }),
    ])
  } finally { clearTimeout(timer) }
}
