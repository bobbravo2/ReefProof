# Default menu system status

Add a compact, read-only status summary to the default attached-TTY `./reefproof`
menu. Refresh it whenever the main menu is entered. Report only ReefProof-owned
state: the effective development or production environment, PID-file-owned daemon
state, processes owned by the current console, and unexpired authenticated sessions
recorded in ReefProof's own database.

Do not inspect unrelated operating-system processes, browser tabs, external Electron
instances, live HYDROS transports, or non-loopback services. Unavailable evidence is
`UNKNOWN`; it is never inferred as healthy.
