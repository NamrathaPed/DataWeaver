import { useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useDropzone } from "react-dropzone";
import { uploadFile, analyzeDataset, selectSheet, type UploadResponse } from "@/services/api";

export default function UploadPage() {
  const navigate = useNavigate();
  const [status, setStatus] = useState<"idle" | "uploading" | "analyzing" | "error">("idle");
  const [error, setError] = useState("");
  const [sheets, setSheets] = useState<string[]>([]);
  const [pendingFile, setPendingFile] = useState<File | null>(null);

  const process = useCallback(async (file: File, sheetName?: string) => {
    try {
      setError("");
      setStatus("uploading");

      let uploadRes: UploadResponse;
      if (sheetName) {
        uploadRes = await selectSheet(file, sheetName);
      } else {
        uploadRes = await uploadFile(file);
      }

      // Multi-sheet Excel — ask user to pick
      if (uploadRes.requires_sheet_selection && uploadRes.sheets) {
        setSheets(uploadRes.sheets);
        setPendingFile(file);
        setStatus("idle");
        return;
      }

      setStatus("analyzing");
      await analyzeDataset(uploadRes.session_id);
      navigate(`/agent/${uploadRes.session_id}`);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Upload failed.";
      setError(msg);
      setStatus("error");
    }
  }, [navigate]);

  const onDrop = useCallback(
    (accepted: File[]) => {
      if (accepted[0]) process(accepted[0]);
    },
    [process]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "text/csv": [".csv"],
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
      "application/vnd.ms-excel": [".xls"],
    },
    maxFiles: 1,
    disabled: status === "uploading" || status === "analyzing",
  });

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-gradient-to-br from-brand-50 to-white px-4">
      {/* Logo / headline */}
      <div className="mb-10 text-center">
        <h1 className="text-4xl font-bold text-gray-900 tracking-tight">
          Data<span className="text-brand-500">Weaver</span>
        </h1>
        <p className="mt-3 text-gray-500 text-lg max-w-md">
          Upload a CSV or Excel file. Get instant cleaning, analysis, charts, and AI insights.
        </p>
      </div>

      {/* Drop zone */}
      <div
        {...getRootProps()}
        className={`w-full max-w-lg border-2 border-dashed rounded-2xl p-12 text-center cursor-pointer transition-all
          ${isDragActive ? "border-brand-500 bg-brand-50" : "border-gray-200 hover:border-brand-400 hover:bg-gray-50"}
          ${status !== "idle" && status !== "error" ? "opacity-60 pointer-events-none" : ""}
        `}
      >
        <input {...getInputProps()} />
        <div className="flex flex-col items-center gap-3">
          <UploadIcon active={isDragActive} />
          {isDragActive ? (
            <p className="text-brand-600 font-medium">Drop it here</p>
          ) : (
            <>
              <p className="text-gray-700 font-medium">Drag & drop your file here</p>
              <p className="text-gray-400 text-sm">or click to browse</p>
              <p className="text-gray-300 text-xs mt-1">CSV, XLSX, XLS — up to 50 MB</p>
            </>
          )}
        </div>
      </div>

      {/* Status */}
      {(status === "uploading" || status === "analyzing") && (
        <div className="mt-6 flex items-center gap-3 text-gray-600">
          <Spinner />
          <span>{status === "uploading" ? "Uploading file..." : "Cleaning & analysing data..."}</span>
        </div>
      )}

      {/* Error */}
      {status === "error" && (
        <div className="mt-6 bg-red-50 border border-red-200 rounded-xl px-5 py-3 text-red-700 text-sm max-w-lg text-center">
          {error}
        </div>
      )}

      {/* Sheet picker */}
      {sheets.length > 0 && pendingFile && (
        <div className="mt-8 card w-full max-w-lg">
          <p className="font-semibold text-gray-800 mb-4">This Excel file has multiple sheets. Pick one:</p>
          <div className="flex flex-wrap gap-2">
            {sheets.map((s) => (
              <button
                key={s}
                className="btn-secondary text-sm"
                onClick={() => {
                  setSheets([]);
                  process(pendingFile, s);
                }}
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function UploadIcon({ active }: { active: boolean }) {
  return (
    <svg
      className={`w-12 h-12 ${active ? "text-brand-500" : "text-gray-300"} transition-colors`}
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={1.5}
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5"
      />
    </svg>
  );
}

function Spinner() {
  return (
    <svg className="animate-spin h-5 w-5 text-brand-500" viewBox="0 0 24 24" fill="none">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8v8H4z"
      />
    </svg>
  );
}
