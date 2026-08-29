"""Read-only authored-system source boundaries and normalization."""

from reefproof.authored_sources.acceptance import accept_source_session, reject_source_session
from reefproof.authored_sources.candidates import (
    canonical_subject_id,
    import_candidates,
    record_candidate_values,
)
from reefproof.authored_sources.google_sheets import (
    GoogleServiceAccountCredentialProvider,
    GoogleSheetsSource,
)
from reefproof.authored_sources.loading import LoadedAuthoredImport, load_authored_source
from reefproof.authored_sources.models import (
    AuthoredImportBatch,
    AuthoredSourceConfiguration,
    AuthoredSourceFetchAttempt,
    AuthoredSourceSnapshot,
    AuthoredSourceStatus,
    AuthoredSourceTab,
    ImportDiagnostic,
    NormalizedSourceRecord,
    SourceHealth,
    SourceTabName,
)
from reefproof.authored_sources.normalize import normalize_source_snapshot
from reefproof.authored_sources.protocol import AuthoredSystemSource, CredentialProvider
from reefproof.authored_sources.review import (
    AuthoredImportReview,
    ExternalIdentityBinding,
    ImportChangeState,
    ImportFactChange,
    ImportObjectReview,
    build_import_review,
)
from reefproof.authored_sources.status import authored_source_status
from reefproof.authored_sources.store import AuthoredSourceStore

__all__ = [
    "AuthoredImportBatch",
    "AuthoredImportReview",
    "AuthoredSourceConfiguration",
    "AuthoredSourceFetchAttempt",
    "AuthoredSourceSnapshot",
    "AuthoredSourceStatus",
    "AuthoredSourceStore",
    "AuthoredSourceTab",
    "AuthoredSystemSource",
    "CredentialProvider",
    "ExternalIdentityBinding",
    "GoogleServiceAccountCredentialProvider",
    "GoogleSheetsSource",
    "ImportChangeState",
    "ImportDiagnostic",
    "ImportFactChange",
    "ImportObjectReview",
    "LoadedAuthoredImport",
    "NormalizedSourceRecord",
    "SourceHealth",
    "SourceTabName",
    "accept_source_session",
    "authored_source_status",
    "build_import_review",
    "canonical_subject_id",
    "import_candidates",
    "load_authored_source",
    "normalize_source_snapshot",
    "record_candidate_values",
    "reject_source_session",
]
