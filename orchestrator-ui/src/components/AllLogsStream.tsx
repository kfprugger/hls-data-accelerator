import { useEffect, useMemo, useRef, useState } from 'react';
import { Box, Card, MenuItem, Stack, TextField, Typography } from '@mui/material';
export interface LogEntry { timestamp: string; level: string; message: string; phase?: string | number }
export function AllLogsStream({ logs, autoScroll = false }: { logs: LogEntry[]; autoScroll?: boolean }) {
  const [search, setSearch] = useState('');
  const [level, setLevel] = useState('all');
  const panel = useRef<HTMLDivElement>(null);
  const follow = useRef(true);
  const visible = useMemo(() => logs.filter(log => (level === 'all' || log.level === level || (level === 'warn' && log.level === 'warning')) && (!search || `${log.message} ${log.phase ?? ''}`.toLowerCase().includes(search.toLowerCase()))), [logs, level, search]);
  useEffect(() => { if (autoScroll && follow.current && panel.current) panel.current.scrollTop = panel.current.scrollHeight; }, [visible.length, autoScroll]);
  useEffect(() => { if (autoScroll) follow.current = true; }, [autoScroll]);
  return <Card>
    <Stack spacing={2}>
      <Typography variant="h6">Logs · {visible.length} of {logs.length}</Typography>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
        <TextField label="Log level" select value={level} onChange={event => setLevel(event.target.value)} sx={{ minWidth: { sm: 160 } }}>{['all', 'info', 'success', 'warn', 'error'].map(value => <MenuItem key={value} value={value}>{value === 'all' ? 'All levels' : value}</MenuItem>)}</TextField>
        <TextField label="Search logs" value={search} onChange={event => setSearch(event.target.value)} fullWidth />
      </Stack>
      <Box ref={panel} tabIndex={0} aria-label="Deployment log entries" onScroll={() => { const p = panel.current; if (p) follow.current = p.scrollHeight - p.scrollTop - p.clientHeight < 48; }} sx={{ maxHeight: '60dvh', overflow: 'auto', bgcolor: '#111318', color: '#e2e2ec', borderRadius: 2, p: 2, fontFamily: 'monospace', fontSize: 12 }}>
        {visible.length === 0 && <Typography>No logs match the current filters.</Typography>}
        {visible.map((log, index) => <Box key={`${log.timestamp}-${index}`} sx={{ borderBottom: '1px solid #ffffff12', py: 0.75, display: 'grid', gridTemplateColumns: { xs: '1fr', md: '85px 75px minmax(0,1fr)' }, gap: 1 }}>
          <span>{log.timestamp ? new Date(log.timestamp).toLocaleTimeString() : ''}</span><Box component="strong" sx={{ color: log.level === 'error' ? '#ffb4ab' : ['warn', 'warning'].includes(log.level) ? '#f0ce79' : log.level === 'success' ? '#90d6a5' : '#b7c4ff' }}>{log.level}</Box><span style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{log.message}</span>
        </Box>)}
      </Box>
      <Typography variant="caption">Scroll up to pause following new entries. Return to the bottom to resume.</Typography>
    </Stack>
  </Card>;
}
