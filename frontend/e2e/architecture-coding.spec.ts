import { test, expect } from '@playwright/test';

test('local image is explicitly uploaded and selected for the same project', async ({page}) => {
  const project='11111111-1111-4111-8111-111111111111';
  const image='22222222-2222-4222-8222-222222222222';
  const writes:string[]=[];
  await page.route('**/api/**', async route => {
    const req=route.request(), path=new URL(req.url()).pathname;
    let value:any={};
    if(path.endsWith('/stream'))return route.fulfill({contentType:'text/event-stream',body:': idle\n\n'});
    if(path==='/api/auth/me')value={username:'reviewer',role:'SECURITY_REVIEWER'};
    if(path==='/api/auth/csrf')value={token:'mock-csrf'};
    if(path==='/api/projects')value=[{id:project,repository:'test/Lichu'}];
    if(path==='/api/dashboard/overview')value={project:{id:project,repository:'test/Lichu'},completedScans:0};
    if(req.method()==='POST'){
      writes.push(path);
      expect(req.headers()['x-csrf-token']).toBe('mock-csrf');
      if(path.endsWith('/architectures')){
        expect(req.headers()['content-type']).toContain('multipart/form-data');
        value={id:image};
      }else value={architectureId:image,selected:true};
    }
    await route.fulfill({json:value});
  });
  await page.goto(`/dashboard?project=${project}&view=architecture`);
  await page.locator('input[type=file]').setInputFiles({name:'diagram.png',mimeType:'image/png',
    buffer:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=','base64')});
  await page.locator('.folder-modal').getByRole('button',{name:'업로드',exact:true}).click();
  expect(writes).toEqual([]);
  await page.locator('.folder-toggle').click();
  await page.locator('.thumb').click();
  await page.getByRole('button',{name:'코딩 Agent에 연결',exact:true}).click();
  await expect.poll(()=>writes.length).toBe(2);
  expect(writes).toEqual([`/api/projects/${project}/architectures`,`/api/projects/${project}/architectures/${image}/select-for-coding`]);
  await expect(page.getByText('아키텍처가 연결되었습니다.',{exact:false})).toBeVisible();
});
