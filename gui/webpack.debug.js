const { merge } = require('webpack-merge');
const common = require('./webpack.common.js');
const path = require('path');

module.exports = merge(common,{
    mode: 'development',
    output: {
      path: path.resolve(__dirname, 'build','debug')
    },
    devtool:"source-map",
    devServer: {
        contentBase: path.resolve(__dirname,'./build','debug'),
      },
});