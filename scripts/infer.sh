#!bash

# usage: hzjchzjc infer.sh 测试语音 sp

set -ex

input_txt=$1
model_name=$2

echo "Inferencing $input_txt with $model_name"

account="hzjc"
password="hzjchzjc"
host="http://101.42.42.44:3333"

# login
token=$(curl --fail -X POST -H "Content-Type: application/json" -d "{\"account\":\"$account\",\"password\":\"$password\"}" $host/user/login)
# remove "" in token
token=$(echo $token | sed 's/\"//g')

# infer
res=$(curl --fail -X POST -H "Content-Type: application/json" -d "{\"text\":\"$input_txt\",\"model_name\":\"$model_name\"}" -H "Authorization: Bearer $token" $host/infer/text2video)
task_id=$(echo $res | jq '.task_id')

echo $res \n

echo $task_id
file_id=0

while true; do
    list=$(curl --fail -X GET -H "Authorization: Bearer $token" $host/tasks?task_id=$task_id)
    # if list[0].status is 2, break
    status=$(echo $list | jq '.[0].status')
    file_id=$(echo $list | jq '.[0].res.output_video_file_id')
    if [ $status -eq 2 ]; then
        break
    fi
    # wait 10 seconds
    sleep 10
done

# download
curl --fail -X GET -H "Authorization: Bearer $token" $host/file/download?file_id=$file_id --output ${model_name}_$(date +%s).mp4