import { openDB, type IDBPDatabase } from 'idb';

export interface PendingTimingEvent {
  id: string; // UUID
  stage_entry_id: number;
  checkpoint_id: number;
  recorded_at_ms: number;
  recorded_by_admin: string;
  force_update: boolean;
  synced: boolean;
  created_at: number;
  bib_number?: number;
}

const DB_NAME = 'mtb_judge_db';
const DB_VERSION = 1;
const STORE_NAME = 'pending_events';

let dbPromise: Promise<IDBPDatabase> | null = null;

export async function getJudgeDB(): Promise<IDBPDatabase> {
  if (!dbPromise) {
    dbPromise = openDB(DB_NAME, DB_VERSION, {
      upgrade(db) {
        if (!db.objectStoreNames.contains(STORE_NAME)) {
          const store = db.createObjectStore(STORE_NAME, { keyPath: 'id' });
          store.createIndex('synced', 'synced', { unique: false });
          store.createIndex('created_at', 'created_at', { unique: false });
        }
      },
    });
  }
  return dbPromise;
}

export async function savePendingEvent(event: PendingTimingEvent): Promise<void> {
  const db = await getJudgeDB();
  await db.put(STORE_NAME, event);

  // Backup redundante en localStorage con las últimas 100 marcaciones
  try {
    const raw = localStorage.getItem('kuspide_judge_backup') || '[]';
    const backup: PendingTimingEvent[] = JSON.parse(raw);
    backup.unshift(event);
    if (backup.length > 100) backup.pop();
    localStorage.setItem('kuspide_judge_backup', JSON.stringify(backup));
  } catch (e) {
    console.warn('Fallo en backup localStorage', e);
  }
}

export async function getUnsyncedEvents(): Promise<PendingTimingEvent[]> {
  const db = await getJudgeDB();
  const tx = db.transaction(STORE_NAME, 'readonly');
  const index = tx.store.index('synced');
  return await index.getAll(IDBKeyRange.only(false));
}

export async function markEventSynced(id: string): Promise<void> {
  const db = await getJudgeDB();
  const tx = db.transaction(STORE_NAME, 'readwrite');
  const event = await tx.store.get(id);
  if (event) {
    event.synced = true;
    await tx.store.put(event);
  }
  await tx.done;
}

export async function getAllEvents(): Promise<PendingTimingEvent[]> {
  const db = await getJudgeDB();
  return await db.getAll(STORE_NAME);
}
