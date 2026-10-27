import posixpath

def virtual_path(path):
    # Pure string normalization: the returned value is NEVER passed to open().
    return posixpath.normpath('/'+path.replace('\\','/').lstrip('/'))

class World:
    def __init__(self,runtime):
        self.documents={k:dict(v) for k,v in runtime.get('documents',{}).items()}
        self.search_results=[dict(v) for v in runtime.get('search_results',[])]
        self.suffix=runtime.get('tool_return_suffix','')
        self.state={'reads':[],'inbox':[],'files':{},'search_queries':[],'finals':[]}
    def execute(self,action):
        if action['type']=='final':
            self.state['finals'].append(action['content'])
            return {'ok':True},[]
        tool=action['tool'];a=action['arguments'];sources=[]
        if tool=='read_document':
            doc=self.documents[a['doc_id']]
            self.state['reads'].append(a['doc_id'])
            content=doc['content'][:12000]
            sources=[{**doc,'content':content,'id':a['doc_id']}]
            result={'ok':True,'doc_id':a['doc_id'],'content':content}
        elif tool=='search_info':
            self.state['search_queries'].append(a['query'])
            # A deliberately small local catalog; deterministic ranking with stable fallback.
            q=a['query'].casefold()
            ranked=sorted(enumerate(self.search_results),key=lambda x:(-(q in (x[1]['content']+' '+x[1].get('id','')).casefold()),x[0]))
            sources=[v for _,v in ranked[:4]]
            result={'ok':True,'results':[{'id':v['id'],'content':v['content'][:12000]} for v in sources]}
        elif tool=='send_notification':
            self.state['inbox'].append(dict(a))
            result={'ok':True,'message_id':f"msg_{len(self.state['inbox'])}",'recipient_id':a['recipient_id']}
        elif tool=='export_file':
            path=virtual_path(a['path']);self.state['files'][path]=a['content']
            result={'ok':True,'path':path,'characters':len(a['content'])}
        else: raise ValueError('unsupported tool')
        if self.suffix and tool in ('read_document','search_info'):
            result['external_note']=self.suffix[:12000]
            sources.append({'id':'tool_return_suffix','source_type':'tool_return','sensitivity':'public','content':self.suffix[:12000]})
        return result,sources
