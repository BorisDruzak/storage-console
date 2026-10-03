export class ReadResponse extends Response {
  constructor(body?:BodyInit | null,init:ResponseInit={}){
    const headers=new Headers(init.headers);
    if (!headers.has('X-Evidence-Valid-For-Ms')) headers.set('X-Evidence-Valid-For-Ms','35000');
    super(body,{...init,headers});
  }
}
