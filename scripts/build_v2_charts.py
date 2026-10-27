"""Render current scientific charts with the project's locked matplotlib."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
ROOT=Path(__file__).resolve().parents[1]
def main():
    font=FontProperties(fname='C:/Windows/Fonts/msyh.ttc')
    out=ROOT/'docs/v2/qa/figures';out.mkdir(parents=True,exist_ok=True)
    for campaign,title in [('baseline','2.0 原基线集'),('external','2.0 公开来源适配集')]:
        s=json.loads((ROOT/'results/v2'/campaign/'summary.json').read_text('utf8'))
        modes=s['modes'];names=['none','input_filter','taint_policy','policy_only']
        fig,axes=plt.subplots(1,2,figsize=(10.5,3.7),layout='constrained')
        for ax,key,label,color in [(axes[0],'asr','攻击成功率','#ae4c3d'),(axes[1],'normal_completion_rate','正常完成率','#24766b')]:
            values=[100*(modes[n].get(key) or 0) for n in names]
            bars=ax.barh(names[::-1],values[::-1],color=color,height=.62)
            ax.set_xlim(0,110);ax.set_xticks([0,25,50,75,100]);ax.set_xlabel('%');ax.set_title(label,fontproperties=font,fontsize=12)
            for b,v in zip(bars,values[::-1]):ax.text(v+1,b.get_y()+b.get_height()/2,f'{v:.1f}%',va='center',fontsize=9)
            ax.spines[['top','right']].set_visible(False)
        fig.suptitle(title+' 实际记录 '+str(s['total_runs'])+' 次',fontproperties=font,fontsize=14)
        fig.savefig(out/(campaign+'.png'),dpi=180);plt.close(fig)
if __name__=='__main__':main()
