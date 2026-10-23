import { test, expect } from '@playwright/test';

test('diagram analysis upload and explicit coding selection coexist for the same project', async ({page}) => {
  const project='11111111-1111-4111-8111-111111111111';
  const image='22222222-2222-4222-8222-222222222222';
  const writes:string[]=[];
  let diagramUploaded=false;
  await page.route('**/api/**', async route => {
    const req=route.request(), path=new URL(req.url()).pathname;
    let value:any={};
    if(path.endsWith('/stream'))return route.fulfill({contentType:'text/event-stream',body:': idle\n\n'});
    if(path==='/api/auth/me')value={username:'reviewer',role:'SECURITY_REVIEWER'};
    if(path==='/api/auth/csrf')value={token:'mock-csrf'};
    if(path==='/api/projects')value=[{id:project,repository:'test/Lichu'}];
    if(path==='/api/dashboard/overview')value={project:{id:project,repository:'test/Lichu'},completedScans:0};
    if(path===`/api/projects/${project}/architecture` && req.method()==='GET'){
      if(!diagramUploaded)return route.fulfill({status:404,json:{}});
      value={status:'EXTRACTED',summary:'분리된 실습 환경입니다.',components:[{name:'Lab',role:'실습 API',isolationStatus:'ISOLATED',state:'OBSERVED'}],confirmed:false};
    }
    if(req.method()==='POST'){
      writes.push(path);
      expect(req.headers()['x-csrf-token']).toBe('mock-csrf');
      if(path.endsWith('/architecture')){
        diagramUploaded=true;
        expect(req.headers()['content-type']).toContain('multipart/form-data');
        value={id:image,status:'QUEUED'};
      }else if(path.endsWith('/architectures')){
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
  await expect.poll(()=>writes.length).toBe(1);
  expect(writes).toEqual([`/api/projects/${project}/architecture`]);
  await expect(page.getByText('분리된 실습 환경입니다.',{exact:true})).toBeVisible();
  await page.locator('.folder-toggle').click();
  await page.locator('.thumb').click();
  await page.getByRole('button',{name:'코딩 Agent에 연결',exact:true}).click();
  await expect.poll(()=>writes.length).toBe(3);
  expect(writes).toEqual([`/api/projects/${project}/architecture`,`/api/projects/${project}/architectures`,`/api/projects/${project}/architectures/${image}/select-for-coding`]);
  await expect(page.getByText('아키텍처가 연결되었습니다.',{exact:false})).toBeVisible();
});
