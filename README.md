# 常见命令汇总

## 单独演示步进电机2往复
 python common\stepper_control.py --port COM3 --position 30000 --command-template "M2:CYCLE:{position}" --ack-wait-seconds 45
## 可选择模型地测试
 C:\Users\rosmo\Desktop\Project\CONTEST\yolo-based-shell-opening-control\control_flows\double_stepper_follow_cycle.py --dry-run --conf 0.05 --weights C:\Users\rosmo\Desktop\Project\CONTEST\yolo-based-shell-opening-control\runs\detect\train\weights\best.pt

 
