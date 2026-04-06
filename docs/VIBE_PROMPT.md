# Vibe Code Prompt

Generate a Chrome Extension Manifest V3 project in TypeScript for a pure frontend video downloader targeting `jable.tv`.

## Core requirements

1. Do not use any backend service.
2. Use Vite + TypeScript.
3. Keep the code modular and layered.
4. Support only Phase 1 for now.
5. The extension must be runnable, not just interface stubs.

## Required project structure

```text
src/
  background/
  content/
  core/
    provider/
    downloader/
    storage/
    models/
  popup/
```

## Functional scope for Phase 1

Implement a minimum viable version that can:

- detect whether the current tab is a supported `jable.tv` video page
- extract:
  - `title`
  - `coverUrl`
  - `videoId`
  - `pageUrl`
  - `m3u8Url`
- display current video info in popup
- create one download task
- fetch and parse the m3u8 playlist
- fetch the encryption key and iv when present
- download ts segments sequentially
- decrypt ts segments with AES-CBC
- merge all segments into a Blob
- trigger browser download of the final mp4
- show task progress in popup
- allow canceling the current task
- persist recent task history in `chrome.storage.local`

## Architecture constraints

- `content script` only extracts metadata from the page
- `background` owns task orchestration
- `popup` only renders UI and sends commands
- core logic must live under `src/core`
- provider logic and downloader logic must be separate
- storage must be separate from downloader logic
- all message contracts must have explicit TypeScript types
- do not put the whole implementation in a single file

## Required modules

Create at least these modules with working implementations:

- `src/core/provider/base.ts`
- `src/core/provider/jableProvider.ts`
- `src/core/downloader/playlistLoader.ts`
- `src/core/downloader/segmentFetcher.ts`
- `src/core/downloader/decryptor.ts`
- `src/core/downloader/merger.ts`
- `src/core/downloader/downloadTask.ts`
- `src/core/storage/taskRepo.ts`
- `src/background/taskManager.ts`
- `src/background/index.ts`
- `src/content/index.ts`
- `src/popup/App.tsx`

## Required data models

Define clear TypeScript types for:

- `VideoMetadata`
- `DownloadTask`
- `DownloadTaskStatus`
- `PlaylistInfo`
- popup/background/content message payloads

## UI requirements

Popup must include:

- current video card
- cover image if available
- title
- download button
- task list
- progress bar
- status label
- error message area

Keep the UI simple and readable.

## Extraction requirements

For `jable.tv`:

- use meta tags to read title and cover
- detect video pages by URL pattern
- extract the m3u8 URL from page source using a practical implementation

## Manifest requirements

Use Manifest V3 and include:

- popup
- background service worker
- content script
- permissions:
  - `storage`
  - `downloads`
  - `tabs`
  - `scripting`
  - `activeTab`
- host permissions for:
  - `jable.tv`
  - playlist and segment requests

## Error handling requirements

Use structured error categories instead of raw `console.error` only.

At minimum support these categories:

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

## Important exclusions

Do not implement these yet:

- multi-task concurrent downloads
- resume after browser restart
- IndexedDB persistence
- multi-site provider support beyond structure
- advanced file streaming optimization

## Output expectation

Produce a complete Phase 1 codebase scaffold with minimal but runnable implementations, preserving clean architecture and future extensibility.
