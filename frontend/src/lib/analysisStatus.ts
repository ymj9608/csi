export function hasAnalysisText(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0;
}

export function analysisStatus(status?: string, analysis?: { red?: string; blue?: string }) {
  switch (status) {
    case 'QUEUED':
      return { title: '분석 대기', detail: '검사가 대기열에 있습니다. 아직 분석이 완료되지 않았습니다.' };
    case 'RUNNING':
      return { title: '분석 진행 중', detail: '검사를 실행하고 있습니다. 현재 표시되는 내용은 최종 결과가 아닙니다.' };
    case 'FAILED':
      return { title: '분석 실패 · 작업 종료', detail: '이 검사는 실패로 종료되어 기다려도 결과가 추가되지 않습니다. 남아 있는 내용은 일부 결과이며, 검사 상세의 실행 기록에서 실패 원인을 확인하세요.' };
    case 'COMPLETED':
      return hasAnalysisText(analysis?.red) && hasAnalysisText(analysis?.blue)
        ? { title: '분석 완료', detail: '완료된 검사에 저장된 분석 결과입니다.' }
        : { title: '검사 완료 · 분석 결과 누락', detail: '검사는 완료됐지만 이 항목의 분석 내용이 일부 또는 전부 저장되지 않았습니다. 검사 상세의 실행 기록을 확인하세요.' };
    default:
      return { title: '분석 상태 확인 필요', detail: '검사 상태를 확인할 수 없습니다. 새로고침하거나 검사 상세에서 상태를 확인하세요.' };
  }
}

export function generationBlockedReason(status?: string): string {
  switch (status) {
    case 'COMPLETED': return '';
    case 'QUEUED': return '검사가 대기 중입니다. 검사가 완료되면 수정안을 요청할 수 있습니다.';
    case 'RUNNING': return '분석이 진행 중입니다. 검사가 완료되면 수정안을 요청할 수 있습니다.';
    case 'FAILED': return '분석이 실패로 종료되어 이 검사에서는 수정안을 생성할 수 없습니다. 실행 기록에서 원인을 확인한 뒤, 완료된 검사의 위험 항목에서 요청하세요.';
    default: return '검사 완료 여부를 확인할 수 없어 수정안 생성을 사용할 수 없습니다. 새로고침하거나 검사 상세를 확인하세요.';
  }
}
