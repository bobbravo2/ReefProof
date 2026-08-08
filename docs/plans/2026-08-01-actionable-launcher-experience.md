# Actionable launcher experience

Implement the accepted `./reefproof` initial-experience plan: state-aware
Workbench lifecycle actions, process-ownership boundaries, useful diagnostics,
configured rotating backup destinations, Desktop reuse of the configured
Workbench, and real PTY/process acceptance. Command history remains disposable
operator convenience data outside backup and release guarantees.

The permanent HYDROS boundary remains unchanged. All service probes are local,
read-only observations; only PID-file-owned ReefProof processes may be stopped
or restarted.
