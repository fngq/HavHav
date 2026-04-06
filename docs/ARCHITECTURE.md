# Chrome Extension Architecture

## Goal

Build a pure frontend Chrome extension that can detect supported video pages, extract downloadable metadata, download encrypted HLS media, decrypt and merge segments in the browser, and save the final mp4 without any backend service.

Primary target:

- `jable.tv`

Core constraints:

- Chrome Extension Manifest V3
- TypeScript
- No Python or server dependency
- Architecture must be extensible to additional sites

## Delivery Plan

### Phase 1

Deliver a minimum viable extension that can:

- detect whether the current page is supported
- extract `title`, `coverUrl`, `videoId`, `pageUrl`, `m3u8Url`
- show current page info in popup
- start a single download task
- fetch playlist, key, and ts segments
- decrypt segments in browser
- merge media into a Blob
- trigger browser download
- show progress and error state
- cancel the current task
- persist recent task history in `chrome.storage.local`

### Phase 2

Extend the extension with:

- multi-task queue
- parallel segment download
- retry logic
- pause and resume
- IndexedDB persistence
- larger file handling improvements
- multi-site provider support

## Layered Design

### UI Layer

Location:

- `src/popup`
- `src/options`

Responsibilities:

- present current page metadata
- display tasks and progress
- collect user actions
- forward actions to background

Rules:

- no download logic
- no page parsing logic

### Content Script Layer

Location:

- `src/content`

Responsibilities:

- inspect the active page
- detect supported pages
- extract video metadata from DOM and page source
- respond to background requests

Rules:

- no task orchestration
- no file download pipeline

### Background Layer

Location:

- `src/background`

Responsibilities:

- own task lifecycle
- manage in-memory task state
- coordinate downloader core
- emit progress updates
- persist task summaries

Rules:

- all task state transitions go through task manager

### Core Layer

Location:

- `src/core`

Responsibilities:

- provider abstraction
- playlist loading and parsing
- segment fetching
- key loading
- AES decryption
- Blob merge
- task persistence helpers

Rules:

- keep business logic independent from popup and DOM where possible

## Key Modules

### Provider

Files:

- `src/core/provider/base.ts`
- `src/core/provider/jableProvider.ts`

Responsibilities:

- determine whether a URL is supported
- extract structured metadata from a document

Output:

- `VideoMetadata`

### Task Manager

Files:

- `src/background/taskManager.ts`

Responsibilities:

- create tasks
- start tasks
- cancel tasks
- update status and progress
- broadcast changes to popup

### Downloader

Files:

- `src/core/downloader/downloadTask.ts`
- `src/core/downloader/playlistLoader.ts`
- `src/core/downloader/segmentFetcher.ts`
- `src/core/downloader/decryptor.ts`
- `src/core/downloader/merger.ts`

Responsibilities:

- run the download pipeline end to end

Execution flow:

1. load playlist
2. parse segment urls, key url, and iv
3. fetch key if encrypted
4. download segments sequentially in Phase 1
5. decrypt segments if needed
6. merge chunks
7. save the result

### Storage

Files:

- `src/core/storage/taskRepo.ts`
- `src/core/storage/settingsRepo.ts`

Responsibilities:

- persist recent tasks
- persist settings
- support later migration to IndexedDB

## Data Models

### VideoMetadata

```ts
type VideoMetadata = {
  site: "jable"
  pageUrl: string
  videoId: string
  title: string
  coverUrl?: string
  m3u8Url: string
}
```

### DownloadTask

```ts
type DownloadTaskStatus =
  | "idle"
  | "pending"
  | "running"
  | "success"
  | "failed"
  | "canceled"

type DownloadTask = {
  id: string
  videoId: string
  title: string
  pageUrl: string
  coverUrl?: string
  m3u8Url: string
  status: DownloadTaskStatus
  progress: number
  totalSegments?: number
  downloadedSegments?: number
  error?: string
  fileName?: string
  createdAt: number
  updatedAt: number
}
```

### PlaylistInfo

```ts
type PlaylistInfo = {
  playlistUrl: string
  segmentUrls: string[]
  keyUrl?: string
  iv?: string
}
```

## Messaging Contracts

At minimum define:

- extract metadata request/response
- create task request/response
- cancel task request/response
- task progress update event
- task snapshot event

All message payloads must have explicit TypeScript types.

## Manifest Requirements

Manifest must include:

- `manifest_version: 3`
- popup entry
- background service worker
- content script registration
- permissions for:
  - `storage`
  - `downloads`
  - `tabs`
  - `scripting`
  - `activeTab`
- host permissions for:
  - `jable.tv`
  - `m3u8`
  - `ts`

## Error Handling

Standardized error categories:

- `UNSUPPORTED_PAGE`
- `METADATA_NOT_FOUND`
- `M3U8_FETCH_FAILED`
- `PLAYLIST_PARSE_FAILED`
- `KEY_FETCH_FAILED`
- `SEGMENT_FETCH_FAILED`
- `DECRYPT_FAILED`
- `MERGE_FAILED`
- `DOWNLOAD_SAVE_FAILED`
- `TASK_CANCELED`

Requirements:

- map every internal error to a user-facing message
- expose short messages in popup
- keep optional debug detail for development

## Generation Constraints

These rules must stay stable during code generation:

- use TypeScript everywhere
- use Manifest V3
- keep provider, downloader, storage, UI, and background separated
- content script only extracts metadata
- popup only renders and sends commands
- background owns orchestration
- avoid giant single-file implementations
- keep future multi-site support possible

## Recommended First Output

Generate only the Phase 1 minimum viable project first:

- Vite project scaffold
- manifest
- popup
- content script
- background
- Jable provider
- task manager
- sequential downloader pipeline
- task history via `chrome.storage.local`

Do not attempt Phase 2 features in the first generation pass.
