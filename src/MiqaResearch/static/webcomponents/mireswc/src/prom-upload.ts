import { LitElement, css, html, type TemplateResult } from 'lit'
import { customElement, property, state, query } from 'lit/decorators.js'

/**
 * File status types
 */
type UploadStatus = 'pending' | 'uploading' | 'completed' | 'error'

/**
 * Interface for tracking selected files
 */
interface SelectedFile {
  file: File
  status: UploadStatus
  progress: number
}

/**
 * Component for uploading patient reported outcome forms.
 * Supports drag and drop and file picker selection.
 */
@customElement('prom-upload')
export class PromUpload extends LitElement {
  @property({ type: String })
  public language: string = "en"

  @property({ type: String })
  public uploadUrl: string = ""

  @property({ type: String })
  public projectId: string = ""

  @state()
  private files: SelectedFile[] = []

  @state()
  private isDragging = false

  @state()
  private globalProgress = 0

  @query('#fileInput')
  private fileInput!: HTMLInputElement

  static styles = css`
    :host {
      --primary: var(--color-primary, #aa3bff);
      --primary-hover: hsl(var(--color-primary-parts, 273 74% 53%) / .5);
      --bg: var(--color-background, #ffffff);
      --text: hsl(var(--color-muted-foreground-parts, 267 8% 42%));
      --text-h: var(--color-muted-foreground, hsl(257, 37%, 4%));
      --border: var(--border-color, #e5e4e7);
      --error: var(--color-chart-error, hsl(0, 84%, 60%));
      --success: var(--color-chart-success, #22c55e);
      --progress-bg: #f4f3ec;

      display: block;
      font-family: system-ui, 'Segoe UI', Roboto, sans-serif;
      color: var(--text);
      margin: 0 auto;
      box-sizing: border-box;
    }

    .drop-zone {
      border: 2px dashed var(--border);
      border-radius: 8px;
      padding: 40px;
      text-align: center;
      cursor: pointer;
      transition: all 0.2s ease;
      background: var(--bg);
      margin-bottom: 24px;
    }
    
    .drop-zone:hover {
      border-color: var(--primary);
    }

    .drop-zone.dragging {
      border-color: var(--primary);
      background: rgba(170, 59, 255, 0.05);
    }

    .drop-zone p {
      margin: 0;
      font-size: 16px;
    }

    .card {
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 20px;
      background: var(--bg);
      box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }

    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 16px;
    }

    .card-title {
      font-size: 20px;
      font-weight: 600;
      color: var(--text-h);
      margin: 0;
    }

    .btn-upload {
      background: var(--primary);
      color: white;
      border: none;
      padding: 8px 16px;
      border-radius: 6px;
      font-weight: 500;
      cursor: pointer;
      transition: background 0.2s;
    }

    .btn-upload:hover {
      background: var(--primary-hover);
    }

    .btn-upload:disabled {
      background: var(--border);
      cursor: not-allowed;
    }

    .progress-container {
      height: 8px;
      background: var(--progress-bg);
      border-radius: 4px;
      overflow: hidden;
      margin-bottom: 20px;
    }

    .progress-bar {
      height: 100%;
      background: var(--primary);
      transition: width 0.3s ease;
    }

    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }

    th {
      text-align: left;
      padding: 12px 8px;
      border-bottom: 1px solid var(--border);
      color: var(--text-h);
    }

    td {
      padding: 12px 8px;
      border-bottom: 1px solid var(--border);
    }

    .status-icon {
      width: 20px;
      height: 20px;
      display: inline-block;
      vertical-align: middle;
    }

    .icon-pending {
      color: var(--text);
    }

    .icon-success {
      color: var(--success);
    }

    .icon-error {
      color: var(--error);
    }

    .btn-remove {
      background: none;
      border: none;
      color: var(--text);
      cursor: pointer;
      padding: 4px;
      border-radius: 4px;
      transition: background 0.2s;
    }

    .btn-remove:hover {
      background: #fef2f2;
      color: var(--error);
    }

    .hidden {
      display: none;
    }
  `

  private handleDragOver(e: DragEvent) {
    e.preventDefault()
    e.stopPropagation()
    this.isDragging = true
  }

  private handleDragLeave(e: DragEvent) {
    e.preventDefault()
    e.stopPropagation()
    this.isDragging = false
  }

  private handleDrop(e: DragEvent) {
    e.preventDefault()
    e.stopPropagation()
    this.isDragging = false
    
    if (e.dataTransfer?.files) {
      this.addFiles(e.dataTransfer.files)
    }
  }

  private openFilePicker() {
    this.fileInput.click()
  }

  private handleFileChange(e: Event) {
    const input = e.target as HTMLInputElement
    if (input.files) {
      this.addFiles(input.files)
    }
  }

  private addFiles(fileList: FileList) {
    const newFiles: SelectedFile[] = []
    for (let i = 0; i < fileList.length; i++) {
      const file = fileList[i]
      // Accept PDF and images as per requirements
      if (file.type === 'application/pdf' || file.type.startsWith('image/')) {
        newFiles.push({
          file,
          status: 'pending',
          progress: 0
        })
      }
    }
    this.files = [...this.files, ...newFiles]
    // Reset input so the same file can be selected again
    this.fileInput.value = ''
  }

  private removeFile(index: number) {
    this.files = this.files.filter((_, i) => i !== index)
  }

  private getCsrfToken(): string | null {
    const name = 'csrftoken'
    let cookieValue: string | null = null
    if (document.cookie && document.cookie !== '') {
      const cookies = document.cookie.split(';')
      for (let i = 0; i < cookies.length; i++) {
        const cookie = cookies[i].trim()
        if (cookie.substring(0, name.length + 1) === (name + '=')) {
          cookieValue = decodeURIComponent(cookie.substring(name.length + 1))
          break
        }
      }
    }
    return cookieValue
  }

  private async uploadFiles() {
    if (this.files.length === 0 || !this.uploadUrl) return

    // Filter files that are not yet uploaded or had an error
    const filesToUpload = this.files.map((f, index) => ({ f, index }))
      .filter(({ f }) => f.status === 'pending' || f.status === 'error')

    if (filesToUpload.length === 0) return

    this.globalProgress = 0
    let uploadedFilesCount = 0

    const csrfToken = this.getCsrfToken()

    for (const { f, index } of filesToUpload) {
      this.updateFileStatus(index, 'uploading', 0)

      try {
        await this.performUpload(f.file, index, csrfToken)
        this.updateFileStatus(index, 'completed', 100)
      } catch (error) {
        console.error('Upload failed for file:', f.file.name, error)
        this.updateFileStatus(index, 'error', 0)
      }

      uploadedFilesCount++
      this.globalProgress = Math.min((uploadedFilesCount / filesToUpload.length) * 100, 100)
    }
  }

  private performUpload(file: File, index: number, csrfToken: string | null): Promise<void> {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest()
      const formData = new FormData()
      
      formData.append('file', file)
      if (this.projectId && this.projectId.trim() !== '') {
        formData.append('projectId', this.projectId)
      }

      xhr.upload.addEventListener('progress', (e) => {
        if (e.lengthComputable) {
          const progress = Math.round((e.loaded / e.total) * 100)
          this.updateFileStatus(index, 'uploading', progress)
        }
      })

      xhr.addEventListener('load', () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve()
        } else {
          reject(new Error(`HTTP Error: ${xhr.status}`))
        }
      })

      xhr.addEventListener('error', () => reject(new Error('Network error')))
      xhr.addEventListener('abort', () => reject(new Error('Upload aborted')))

      xhr.open('POST', this.uploadUrl)
      
      if (csrfToken) {
        xhr.setRequestHeader('X-CSRFToken', csrfToken)
      }
      
      xhr.send(formData)
    })
  }

  private updateFileStatus(index: number, status: UploadStatus, progress: number) {
    this.files = this.files.map((f, i) => 
      i === index ? { ...f, status, progress } : f
    )
  }


  private formatSize(bytes: number): string {
    if (bytes === 0) return '0 Bytes'
    const k = 1024
    const sizes = ['Bytes', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
  }

  private renderStatusIcon(status: UploadStatus): TemplateResult {
    switch (status) {
      case 'completed':
        return html`
          <svg class="status-icon icon-success" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
            <polyline points="22 4 12 14.01 9 11.01"></polyline>
          </svg>
        `
      case 'error':
        return html`
          <svg class="status-icon icon-error" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"></circle>
            <line x1="15" y2="15" x1="9" y1="9"></line>
            <line x1="9" y2="15" x1="15" y1="9"></line>
          </svg>
        `
      case 'uploading':
        return html`
          <svg class="status-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 12a9 9 0 1 1-6.21-8.58"></path>
          </svg>
        `
      default:
        return html`
          <svg class="status-icon icon-pending" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"></circle>
            <polyline points="12 6 12 12 16 14"></polyline>
          </svg>
        `
    }
  }

  render() {
    this.language = this.language.toLowerCase().split("-")[0];
    let translatedString: string[] = new Array<string>();
    switch (this.language) {
        case "sv":
            translatedString = [
                "Dra och släpp PROM formulär här eller klicka för att välja filer",
                "Stöd för PDF, JPG, PNG",
                "PROM Formulär",
                "Ladda upp filer",
                "Filnamn",
                "Storlek",
                "Status",
            ]
            break;
        default:
            if ( this.language !== "en" ) console.log("Unknown/-implemented language set. Defaulting to english")
            translatedString = [
                "Drag and drop PROM forms here, or click to select files",
                "Supports PDF, JPG, PNG",
                "PROM Forms",
                "Upload Files",
                "File Name",
                "Size",
                "Status",
            ]
    }

    return html`
      <div 
        class="drop-zone ${this.isDragging ? 'dragging' : ''}"
        @dragover=${this.handleDragOver}
        @dragleave=${this.handleDragLeave}
        @drop=${this.handleDrop}
        @click=${this.openFilePicker}
      >
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color: var(--primary); margin-bottom: 12px;">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
          <polyline points="17 8 12 3 7 8"></polyline>
          <line x1="12" x2="12" y1="3" y2="15"></line>
        </svg>
        <p>${translatedString[0]}</p>
        <p style="font-size: 12px; color: var(--text); margin-top: 8px;">${translatedString[1]}</p>
        <input 
          type="file" 
          id="fileInput" 
          class="hidden" 
          multiple 
          accept="application/pdf,image/*"
          @change=${this.handleFileChange}
        >
      </div>
      ${this.files.length === 0 ? html`` : html`
      <div class="card">
        <div class="card-header">
          <h2 class="card-title">${translatedString[2]} (${this.files.length})</h2>
          <button
              class="btn-upload"
              ?disabled=${this.files.length === 0}
              @click=${this.uploadFiles}
          >
            ${translatedString[3]}
          </button>
        </div>

        <div class="progress-container">
          <div class="progress-bar" style="width: ${this.globalProgress}%"></div>
        </div>

        <table>
          <thead>
          <tr>
            <th style="width: 40px;"></th>
            <th>${translatedString[4]}</th>
            <th>${translatedString[5]}</th>
            <th>${translatedString[6]}</th>
            <th style="width: 40px;"></th>
          </tr>
          </thead>
          <tbody>
          ${this.files.map((file, index) => html`
            <tr>
              <td>${this.renderStatusIcon(file.status)}</td>
              <td>${file.file.name}</td>
              <td>${this.formatSize(file.file.size)}</td>
              <td>${file.status.charAt(0).toUpperCase() + file.status.slice(1)}</td>
              <td>
                <button class="btn-remove" @click=${(e: Event) => {
                  e.stopPropagation();
                  this.removeFile(index);
                }}>
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
                       stroke-linecap="round" stroke-linejoin="round">
                    <path d="M3 6h18"></path>
                    <path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"></path>
                    <path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"></path>
                    <line x1="10" x2="10" y1="11" y2="17"></line>
                    <line x1="14" x2="14" y1="11" y2="17"></line>
                  </svg>
                </button>
              </td>
            </tr>
          `)}
          </tbody>
        </table>
      </div>
    `}
    `
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'prom-upload': PromUpload
  }
}